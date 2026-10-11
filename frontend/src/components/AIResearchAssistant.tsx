import { useId, useState, type KeyboardEvent } from 'react';
import { AnalystBrief } from './AnalystBrief';
import { ExplainSignal } from './ExplainSignal';
import { PanelBoundary } from './PanelBoundary';
import { SnowflakeResearch } from './SnowflakeResearch';

const tools = [
  { id: 'context', label: 'Research Context' },
  { id: 'explanation', label: 'Signal Explanation' },
  { id: 'brief', label: 'Listen to Brief' },
] as const;

/** Company/event changes reset the whole assistant; switching tabs never does. */
export function AIResearchAssistant(props: { ticker: string; evidenceKey: string }) {
  return <ResearchAssistantTabs key={`${props.ticker}:${props.evidenceKey}`} {...props} />;
}

function ResearchAssistantTabs({ ticker, evidenceKey }: { ticker: string; evidenceKey: string }) {
  const [selected, setSelected] = useState(0);
  const id = useId();
  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    if (event.key === 'ArrowRight') next = (index + 1) % tools.length;
    else if (event.key === 'ArrowLeft') next = (index + tools.length - 1) % tools.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tools.length - 1;
    else return;
    event.preventDefault();
    setSelected(next);
    event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }
  const panels = [
    <SnowflakeResearch ticker={ticker} />,
    <ExplainSignal ticker={ticker} evidenceKey={evidenceKey} evidence={null} />,
    <AnalystBrief ticker={ticker} evidenceKey={evidenceKey} />,
  ];
  return <section className="ie-stack ie-research-assistant" aria-labelledby={`${id}-heading`}>
    <header className="ie-research-assistant-heading">
      <h2 id={`${id}-heading`}>AI Research Assistant</h2>
      <p className="ie-muted">AI tools interpret existing filing and quantitative evidence. They do not calculate or modify InsiderEdge scores or predictions.</p>
    </header>
    <div className="ie-research-assistant-tabs" role="tablist" aria-label="AI research tools">
      {tools.map((tool, index) => <button key={tool.id} type="button" role="tab"
        id={`${id}-tab-${tool.id}`} aria-controls={`${id}-panel-${tool.id}`}
        aria-selected={selected === index} tabIndex={selected === index ? 0 : -1}
        onClick={() => setSelected(index)} onKeyDown={event => navigate(event, index)}>
        {tool.label}
      </button>)}
    </div>
    {/* Hidden panels stay mounted: retain output, pending requests and audio state. */}
    {tools.map((tool, index) => <div key={tool.id} role="tabpanel" tabIndex={0}
      id={`${id}-panel-${tool.id}`} aria-labelledby={`${id}-tab-${tool.id}`}
      hidden={selected !== index} className="ie-research-assistant-panel">
      <PanelBoundary label={tool.label}>{panels[index]}</PanelBoundary>
    </div>)}
  </section>;
}
