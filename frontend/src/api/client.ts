import { RadarResponse, CompanyResponse, PricesResponse, InsidersResponse } from "../types/api";
import { DEV_MOCK_RADAR, DEV_MOCK_COMPANY, DEV_MOCK_PRICES, DEV_MOCK_INSIDERS } from "./mocks";
import { ApiError, getJson } from './http';
import type { StatisticsResponse, PredictionResponse } from '../types/research';

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || "http://localhost:8000";

// 1. Preserve development mocks only behind an explicit development/demo mechanism
export const usingResearchMocks = Boolean(import.meta.env?.DEV && import.meta.env?.VITE_USE_MOCKS !== 'false');
const USE_MOCKS = usingResearchMocks;

export function mockCompany(ticker: string): CompanyResponse {
  if (ticker.toUpperCase() !== DEV_MOCK_COMPANY.ticker) throw new ApiError(404);
  return structuredClone(DEV_MOCK_COMPANY);
}

// Safely format the base URL to prevent duplicate slashes
const safeBaseUrl = BASE_URL.replace(/\/$/, '');
const companyUrl = (ticker: string) => `${safeBaseUrl}/api/companies/${encodeURIComponent(ticker.toUpperCase())}`;

export const fetchRadar = async (signal?: AbortSignal): Promise<RadarResponse> => {
  if (USE_MOCKS) return structuredClone(DEV_MOCK_RADAR);
  return getJson(`${safeBaseUrl}/api/radar`, signal);
};

export const fetchCompany = async (
  ticker: string,
  signal?: AbortSignal,
): Promise<CompanyResponse> => {
  if (USE_MOCKS) return mockCompany(ticker);
  return getJson(companyUrl(ticker), signal);
};

export const fetchPrices = async (ticker: string, signal?: AbortSignal): Promise<PricesResponse> => {
  if (USE_MOCKS) { 
    mockCompany(ticker); 
    return structuredClone(DEV_MOCK_PRICES); 
  }
  return getJson(`${companyUrl(ticker)}/prices`, signal);
};

export const fetchInsiders = async (ticker: string, signal?: AbortSignal): Promise<InsidersResponse> => {
  if (USE_MOCKS) { 
    mockCompany(ticker); 
    return structuredClone(DEV_MOCK_INSIDERS); 
  }
  return getJson(`${companyUrl(ticker)}/insiders`, signal);
};

export async function fetchStatistics(ticker: string, signal?: AbortSignal): Promise<StatisticsResponse> {
  if (USE_MOCKS) throw new ApiError(503); // Prevent inventing fake statistical evidence
  return getJson(`${companyUrl(ticker)}/statistics`, signal);
}

export async function fetchPrediction(ticker: string, signal?: AbortSignal): Promise<PredictionResponse> {
  if (USE_MOCKS) throw new ApiError(503); // Prevent inventing fake ML results
  return getJson(`${companyUrl(ticker)}/prediction`, signal);
}