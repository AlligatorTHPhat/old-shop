import { SalesReport } from '../../../core/models';

export function salesChart(report: SalesReport | null | undefined, view: 'year' | 'month', month: number) {
  if (!report?.available) return { labels: [] as string[], values: [] as number[] };
  const count = view === 'year' ? 12 : new Date(report.year, month, 0).getDate();
  const values = Array<number>(count).fill(0);
  for (const row of report.daily) {
    const [year, rowMonth, day] = row.day.split('-').map(Number);
    if (year !== report.year || (view === 'month' && rowMonth !== month)) continue;
    const index = view === 'year' ? rowMonth - 1 : day - 1;
    if (index >= 0 && index < count) values[index] += Number(row.gross_sales_vnd);
  }
  return {
    labels: Array.from({ length: count }, (_, i) => `${view === 'year' ? 'T' : 'Ngày '}${i + 1}`),
    values,
  };
}
