"""Synthetic correctness fixtures only, including fake historical attestations."""
from copy import deepcopy
import json
import socket
import pytest
from research.provisional_score_evaluation import evaluate_c_masking


def record(identity="SYNTHETIC:1", **updates):
    row=dict(research_event_id=identity,ticker="SYNTHETIC",information_date="2025-01-02",
             ranking_context="synthetic",evidence_kind="synthetic",
             components={"A":80.,"C":20.,"M":60.,"S":40.,"D":70.},official_score=57.5)
    row.update(updates)
    return row


def attested(identity="SYNTHETIC:1",**updates):
    return record(identity,evidence_kind="historical",provenance={
        "reviewed_no_lookahead":True,"run_id":"synthetic-run","artifact_id":"synthetic-model",
        "model_available_at":"2025-01-01","components":{
            n:{"observed":True,"available_at":"2025-01-02"} for n in "ACMSD"}},**updates)


def run(rows,minimum=2,k=1):
    return evaluate_c_masking(rows,minimum_group_size=minimum,top_k=k)


def test_known_formula_and_errors():
    row=run([record()])["rows"][0]
    assert row["complete_score"]==57.5
    assert row["provisional_score"]==pytest.approx(54.5/.85)
    assert row["observed_weight"]==.85
    assert row["masked_component"]=="C"
    assert row["signed_error"]==pytest.approx(54.5/.85-57.5)
    assert row["absolute_error"]==abs(row["signed_error"])


@pytest.mark.parametrize("c,other,error",[(0,100,15),(100,0,-15),(0,0,0),(100,100,0)])
def test_bound_and_endpoints(c,other,error):
    result=run([record(components={n:c if n=="C" else other for n in "ACMSD"},official_score=None)])
    assert result["rows"][0]["signed_error"]==pytest.approx(error)
    assert result["theoretical_absolute_error_bound"]==15


@pytest.mark.parametrize("value",[True,"60",float("nan"),float("inf"),-1,101])
@pytest.mark.parametrize("name",list("ACMSD"))
def test_invalid_component(value,name):
    row=record();row["components"][name]=value
    with pytest.raises(ValueError,match="finite numeric"):
        run([row])


def test_missing_c_and_wrong_official():
    row=record();row["components"]["C"]=None
    result=run([row])
    assert result["rows"]==[]
    assert result["excluded"][0]["reasons"]==["C:missing"]
    with pytest.raises(ValueError,match="disagrees"):
        run([record(official_score=10)])


def test_formula_without_official_and_no_double_scaling():
    row=record(official_score=None);row["components"]["M"]=1
    assert run([row])["rows"][0]["complete_score"]==pytest.approx(39.8)


def test_malformed_and_duplicate_records():
    for rows,match in [([record(),record()],"duplicate"),([None],"expected mapping"),
                       ([record(information_date="bad")],"ISO"),
                       ([record(components={"A":1})],"exactly"),
                       ([record(research_event_id="")],"nonempty")]:
        with pytest.raises(ValueError,match=match):
            run(rows)


def test_separate_synthetic_and_incomplete_provenance():
    result=run([record(),record("SYNTHETIC:2",evidence_kind="historical")])
    assert result["eligible_historical_count"]==0
    assert result["status"]=="insufficient_data"
    assert result["groups"]==[]
    assert [r["category"] for r in result["rows"]]==["synthetic","historical_provenance_incomplete"]


@pytest.mark.parametrize("name",list("ACMSD"))
def test_future_component(name):
    row=attested();row["provenance"]["components"][name]["available_at"]="2025-01-03"
    with pytest.raises(ValueError,match="after information_date"):
        run([row])


def test_future_model_and_unobserved_component():
    row=attested();row["provenance"]["model_available_at"]="2025-01-03"
    with pytest.raises(ValueError,match="after information_date"):
        run([row])
    row=attested();row["provenance"]["components"]["C"]["observed"]=False
    assert run([row])["eligible_historical_count"]==0


def test_groups_do_not_pool_dates_or_contexts():
    result=run([attested("SYNTHETIC:1"),attested("SYNTHETIC:2"),
                attested("SYNTHETIC:3",information_date="2025-01-03"),
                attested("SYNTHETIC:4",ranking_context="other")])
    assert sorted(g["n"] for g in result["groups"])==[1,1,2]
    assert sum(g["ranking"] is not None for g in result["groups"])==1
    assert all(g["metrics"] is None for g in result["groups"] if g["n"]==1)


def test_numeric_metrics_inversions_and_ties():
    a=attested("SYNTHETIC:A",components={n:100 if n=="C" else 50 for n in "ACMSD"},official_score=None)
    b=attested("SYNTHETIC:B",components={n:0 if n=="C" else 55 for n in "ACMSD"},official_score=None)
    group=run([a,b])["groups"][0]
    assert group["ranking"]["spearman"]==pytest.approx(-1)
    assert group["ranking"]["pairwise_inversions"]==1
    assert group["ranking"]["top_k_overlap_count"]==0
    assert group["metrics"]["mae"]==pytest.approx((7.5+8.25)/2)
    assert group["metrics"]["rmse"]==pytest.approx(((7.5**2+8.25**2)/2)**.5)
    assert group["metrics"]["signed_bias"]==pytest.approx((-7.5+8.25)/2)
    tied=run([attested("SYNTHETIC:B"),attested("SYNTHETIC:A")])["groups"][0]
    assert tied["ranking"]["spearman"] is None
    assert tied["ranking"]["spearman_reason"]=="constant_ranks"
    assert tied["ranking"]["tied_pairs_excluded"]==1
    assert tied["ranking"]["top_k_overlap_fraction"]==1


def test_determinism_immutability_json_no_io(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError("No IO")
    monkeypatch.setattr(socket.socket,"connect",forbidden)
    monkeypatch.setattr("builtins.open",forbidden)
    rows=[attested("SYNTHETIC:B"),attested("SYNTHETIC:A")];original=deepcopy(rows)
    result=run(rows)
    assert result==run(reversed(rows))
    assert rows==original
    json.dumps(result,allow_nan=False)
    result["rows"][0]["ticker"]="changed"
    assert rows==original


@pytest.mark.parametrize("minimum,k",[(1,1),(True,1),(2,2),(2,0)])
def test_explicit_summary_policy(minimum,k):
    with pytest.raises(ValueError):
        run([],minimum,k)


def test_provenance_references_detached_and_allowlisted():
    row=attested();row['provenance']['raw_source']='DO_NOT_EXPORT';original=deepcopy(row)
    result=run([row]);refs=result['rows'][0]['provenance_references']
    assert refs['run_id']=='synthetic-run' and refs['artifact_id']=='synthetic-model'
    assert refs['model_available_at']=='2025-01-01'
    assert refs['component_available_at']=={n:'2025-01-02' for n in 'ACMSD'}
    assert 'DO_NOT_EXPORT' not in json.dumps(result)
    assert result==run([row])
    refs['component_available_at']['A']='changed'
    assert row==original
    assert run([record()])['rows'][0]['provenance_references'] is None


@pytest.mark.parametrize('field',['run_id','artifact_id','model_available_at','components','reviewed_no_lookahead'])
def test_missing_individual_provenance_excludes(field):
    row=attested();del row['provenance'][field]
    result=run([row])
    assert result['eligible_historical_count']==0
    assert result['rows'][0]['provenance_references'] is None
    assert result['rows'][0]['exclusion_reasons']


@pytest.mark.parametrize('field,value',[('root',[]),('components',[]),('item',[]),('date','PRIVATE'),('run_id','PRIVATE SECRET'),('artifact_id','')])
def test_malformed_provenance_sanitized(field,value):
    row=attested()
    if field=='root': row['provenance']=value
    elif field=='item': row['provenance']['components']['A']=value
    elif field=='date': row['provenance']['components']['A']['available_at']=value
    else: row['provenance'][field]=value
    with pytest.raises(ValueError) as caught: run([row])
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('field',['ranking_context','information_date'])
def test_missing_grouping_metadata_rejected(field):
    row=record();del row[field]
    with pytest.raises(ValueError,match=field): run([row])


def test_empty_and_mixed_exclusions():
    empty=run([])
    assert empty['rows']==empty['excluded']==empty['groups']==[]
    assert empty['status']=='insufficient_data'
    row=attested('SYNTHETIC:C');row['components']['C']=None
    result=run([attested('SYNTHETIC:A'),attested('SYNTHETIC:B'),row])
    assert result['eligible_historical_count']==result['groups'][0]['n']==2
    assert result['excluded']==[{'research_event_id':'SYNTHETIC:C','reasons':['C:missing'],
        'evidence_kind':'historical','ranking_context':'synthetic','information_date':'2025-01-02'}]


def test_partial_ties_and_streaming_equivalence():
    # Average ranks [1,2.5,2.5,4] and [1.5,1.5,3,4] give Pearson 5/6.
    rows=[]
    for i,(actual,masked) in enumerate([(10,10),(20,10),(20,20),(30,30)]):
        c=(actual-.85*masked)/.15
        rows.append(attested(f'SYNTHETIC:{i}',components={n:c if n=='C' else masked for n in 'ACMSD'},official_score=None))
    result=run(rows);ranking=result['groups'][0]['ranking']
    assert ranking['spearman']==pytest.approx(5/6)
    output=result['rows'];pairs=[(a,b) for i,a in enumerate(output) for b in output[i+1:]]
    comparable=[(a,b) for a,b in pairs if a['complete_score']!=b['complete_score'] and a['provisional_score']!=b['provisional_score']]
    assert ranking['strictly_comparable_pairs']==len(comparable)
    assert ranking['tied_pairs_excluded']==len(pairs)-len(comparable)
    assert ranking['pairwise_inversions']==sum((a['complete_score']-b['complete_score'])*(a['provisional_score']-b['provisional_score'])<0 for a,b in comparable)
    assert result==run(reversed(rows))


def test_error_percentiles_median_and_max():
    rows=[attested(f'SYNTHETIC:{i}',components={n:c if n=='C' else 0 for n in 'ACMSD'},official_score=None) for i,c in enumerate([0,20,40,60])]
    metrics=run(rows)['groups'][0]['metrics']
    assert metrics['median_absolute_error']==pytest.approx(4.5)
    assert metrics['max_absolute_error']==pytest.approx(9)
    assert metrics['p90_absolute_error']==pytest.approx(8.1)
    assert metrics['p95_absolute_error']==pytest.approx(8.55)
