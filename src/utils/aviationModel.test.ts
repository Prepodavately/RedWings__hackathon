import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CANDIDATE_CITIES,
  scoreCandidateCities,
  calculateHypothesesComparison,
  TOTAL_RF_MARKET_PAX_2025,
} from './aviationModel';

test('scoreCandidateCities ranks all 12 cities and marks exactly 3 as Top-3', () => {
  const scored = scoreCandidateCities(CANDIDATE_CITIES, {
    wPopulation: 30,
    wHubDistance: 20,
    wCompetitorGap: 30,
    wTourismDemand: 20,
  });

  assert.equal(scored.length, 12);
  assert.equal(scored.filter((c) => c.isTop3).length, 3);
  assert.equal(scored[0].rank, 1);
  assert.equal(scored[11].rank, 12);
  assert.ok(scored[0].totalScore >= scored[1].totalScore);
  assert.ok(scored[1].totalScore >= scored[2].totalScore);
});

test('scoreCandidateCities handles zero weights gracefully with equal fallback', () => {
  const scored = scoreCandidateCities(CANDIDATE_CITIES, {
    wPopulation: 0,
    wHubDistance: 0,
    wCompetitorGap: 0,
    wTourismDemand: 0,
  });

  assert.equal(scored.length, 12);
  assert.ok(scored[0].totalScore > 0);
});

test('calculateHypothesesComparison computes passengers, revenue, and market share of 108.9M accurately', () => {
  const res = calculateHypothesesComparison({
    loadFactorPct: 84,
    avgFareRub: 8400,
    weeklyFreqPerRoute: 5,
    aircraftSeats: 100,
    activeRouteCount: 10,
    scenario: 'base',
    selectedHubIata: 'KUF',
  });

  assert.ok(res.hub.annualPassengers > 0);
  assert.ok(res.p2p.annualPassengers > 0);
  assert.ok(res.hub.annualRevenueMlnRub > 0);
  assert.ok(res.p2p.annualRevenueMlnRub > 0);

  const expectedP2pShareDelta = Number(
    ((res.p2p.annualPassengers / TOTAL_RF_MARKET_PAX_2025) * 100).toFixed(3)
  );
  assert.equal(res.p2p.marketShareDeltaPct, expectedP2pShareDelta);
  assert.equal(res.winner, 'p2p');
});

test('conservative scenario reduces passenger volume and increases cost compared to base scenario', () => {
  const base = calculateHypothesesComparison({
    loadFactorPct: 85,
    avgFareRub: 8500,
    weeklyFreqPerRoute: 5,
    aircraftSeats: 100,
    activeRouteCount: 10,
    scenario: 'base',
    selectedHubIata: 'KUF',
  });

  const conservative = calculateHypothesesComparison({
    loadFactorPct: 85,
    avgFareRub: 8500,
    weeklyFreqPerRoute: 5,
    aircraftSeats: 100,
    activeRouteCount: 10,
    scenario: 'conservative',
    selectedHubIata: 'KUF',
  });

  assert.ok(conservative.p2p.annualPassengers < base.p2p.annualPassengers);
  assert.ok(conservative.p2p.operatingCostMlnRub > base.p2p.operatingCostMlnRub);
});
