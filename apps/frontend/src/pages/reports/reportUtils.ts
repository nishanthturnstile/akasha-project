import { ApiError } from '@/lib/api';
import type { FieldLeaderboardRow } from '@/types/api';

export function reportErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Report data could not be loaded.';
}

export function fmt(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return 'n/a';
  if (typeof value === 'number') return Number.isFinite(value) ? value.toFixed(digits) : 'n/a';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

export function valueForColumn(row: FieldLeaderboardRow, column: string): unknown {
  const mapping: Record<string, unknown> = {
    group: row.groupName,
    crop: row.cropType,
    season: row.seasonLabel,
  };
  if (column in mapping) return mapping[column];
  return (row as unknown as Record<string, unknown>)[column];
}

export function downloadFile(file: { blob: Blob; filename: string }) {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename;
  link.click();
  URL.revokeObjectURL(url);
}
