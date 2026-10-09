import { RadarResponse, CompanyResponse, PricesResponse, InsidersResponse } from "../types/api";
import { DEV_MOCK_RADAR, DEV_MOCK_COMPANY, DEV_MOCK_PRICES, DEV_MOCK_INSIDERS } from "./mocks";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const USE_MOCKS = true; // Toggle this when Person 1 finishes the backend

export const fetchRadar = async (): Promise<RadarResponse> => {
  if (USE_MOCKS) return DEV_MOCK_RADAR;
  const res = await fetch(`${BASE_URL}/api/radar`);
  if (!res.ok) throw new Error("Failed to fetch radar");
  return res.json();
};

export const fetchCompany = async (
  ticker: string,
): Promise<CompanyResponse> => {
  if (USE_MOCKS) return DEV_MOCK_COMPANY;
  const res = await fetch(`${BASE_URL}/api/companies/${ticker}`);
  if (!res.ok) throw new Error("Failed to fetch company");
  return res.json();
};

export const fetchPrices = async (ticker: string): Promise<PricesResponse> => {
  if (USE_MOCKS) return DEV_MOCK_PRICES;
  const res = await fetch(`${BASE_URL}/api/companies/${ticker}/prices`);
  if (!res.ok) throw new Error("Failed to fetch prices");
  return res.json();
};

export const fetchInsiders = async (ticker: string): Promise<InsidersResponse> => {
  if (USE_MOCKS) return DEV_MOCK_INSIDERS;
  const res = await fetch(`${BASE_URL}/api/companies/${ticker}/insiders`);
  if (!res.ok) throw new Error("Failed to fetch insiders");
  return res.json();
};