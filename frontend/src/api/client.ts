import { RadarResponse, CompanyResponse } from "../types/api";
import { DEV_MOCK_RADAR, DEV_MOCK_COMPANY } from "./mocks";

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
