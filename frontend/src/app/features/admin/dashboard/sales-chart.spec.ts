import { describe, it, expect } from 'vitest';
import { SalesReport } from '../../../core/models';
import { salesChart } from './sales-chart';

describe('ETL sales chart', () => {
  const report: SalesReport = {
    year: 2024, as_of: '2024-03-01T00:00:00Z', available: true, stale: false,
    gross_sales_vnd: 30,
    daily: [
      { day: '2024-02-28', gross_sales_vnd: 10, item_quantity: 1 },
      { day: '2024-02-29', gross_sales_vnd: 20, item_quantity: 1 },
    ],
  };
  it('sums daily ETL rows into months without synthetic revenue', () => {
    expect(salesChart(report, 'year', 2).values).toEqual([0, 30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  });
  it('keeps leap day and empty months correct', () => {
    const feb = salesChart(report, 'month', 2);
    expect(feb.values.length).toBe(29);
    expect(feb.values[28]).toBe(20);
    expect(salesChart(report, 'month', 4).values).toEqual(Array(30).fill(0));
  });
  it('distinguishes an unavailable report from a real zero', () => {
    expect(salesChart(undefined, 'year', 1).values).toEqual([]);
    expect(salesChart({ ...report, available: false }, 'year', 1).values).toEqual([]);
  });
});
