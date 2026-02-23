import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const ticker = searchParams.get('ticker');

  // Mock data for demonstration
  const mockData = {
    revenue: { growth: 15.2, change: 12.5 },
    netIncome: { growth: 18.7, change: 15.3 },
    eps: { growth: 20.1, change: 18.2 },
    fcf: { growth: 12.9, change: 10.1 },
  };

  return NextResponse.json(mockData);
}
