// Reported trial results are copied from the stored registry record. The view must never invent
// a value, never merge groups, and must keep "no results posted" distinct from "no effect".
const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const context = vm.createContext({
  esc: s => String(s).replace(/[&<>"']/g, c => (
    {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
});
for (const file of ['../web/external-links.js', '../web/trial-results.js']) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
}
const {trialResultsView} = context;

// Shaped like the stored FIBRONEER-IPF record (NCT05321069).
const withResults = () => ({
  summary: {nct_id: 'NCT05321069', has_results: true},
  response: {resultsSection: {
    outcomeMeasuresModule: {outcomeMeasures: [{
      type: 'PRIMARY',
      title: 'Absolute Change From Baseline in FVC [mL] at Week 52',
      paramType: 'LEAST_SQUARES_MEAN', dispersionType: '95% Confidence Interval',
      unitOfMeasure: 'Milliliters (mL)', timeFrame: 'Week 52',
      populationDescription: 'Treated set',
      groups: [{id: 'OG000', title: 'Placebo'}, {id: 'OG002', title: 'Nerandomilast 18 mg BID'}],
      classes: [{categories: [{measurements: [
        {groupId: 'OG000', value: '-183.48', lowerLimit: '-210.86', upperLimit: '-156.10'},
        {groupId: 'OG002', value: '-114.65', lowerLimit: '-141.81', upperLimit: '-87.50'}]}]}],
      analyses: [{groupIds: ['OG000', 'OG002'], pValue: '0.0001', statisticalMethod: 'MMRM'}],
    }, {type: 'SECONDARY', title: 'Time to first exacerbation', groups: [], classes: []}]},
    adverseEventsModule: {
      frequencyThreshold: '5',
      eventGroups: [
        {id: 'EG000', title: 'Placebo', seriousNumAffected: 181, seriousNumAtRisk: 393,
         otherNumAffected: 300, otherNumAtRisk: 393, deathsNumAffected: 20, deathsNumAtRisk: 393},
        {id: 'EG002', title: 'Nera 18 mg BID', seriousNumAffected: 165, seriousNumAtRisk: 392,
         otherNumAffected: 310, otherNumAtRisk: 392, deathsNumAffected: 15, deathsNumAtRisk: 392}],
      seriousEvents: [{term: 'Pneumonia', organSystem: 'Infections', sourceVocabulary: 'MedDRA 27.1',
                       stats: [{groupId: 'EG000', numAffected: 20, numAtRisk: 393},
                               {groupId: 'EG002', numAffected: 12, numAtRisk: 392}]}],
      otherEvents: [{term: 'Diarrhoea', organSystem: 'Gastrointestinal',
                     stats: [{groupId: 'EG000', numAffected: 40, numAtRisk: 393},
                             {groupId: 'EG002', numAffected: 160, numAtRisk: 392}]}]},
  }},
});

test('The primary outcome shows each group with its own interval', () => {
  const html = trialResultsView(withResults());
  assert.match(html, /Absolute Change From Baseline in FVC/);
  assert.match(html, /-114\.65/);
  assert.match(html, /\[-141\.81 ~ -87\.50\]/, 'the confidence interval stays attached');
  assert.match(html, /Placebo/);
  assert.match(html, /-183\.48/);
  assert.match(html, /Milliliters \(mL\)/);
  assert.match(html, /LEAST_SQUARES_MEAN/);
});

test('A group comparison keeps its p-value together with the model', () => {
  const html = trialResultsView(withResults());
  assert.match(html, /p 0\.0001/);
  assert.match(html, /MMRM/, 'a p-value without its model is not interpretable');
  assert.match(html, /Placebo 대 Nerandomilast 18 mg BID/);
});

test('Adverse events are shown as affected over at-risk, not as a verdict', () => {
  const html = trialResultsView(withResults());
  assert.match(html, /181\/393/);
  assert.match(html, /\(46\.1%\)/);
  assert.match(html, /Diarrhoea/);
  assert.match(html, /160\/392/);
  assert.match(html, /MedDRA 27\.1/);
  assert.doesNotMatch(html, /안전|위험도 점수/, 'no safety judgement is produced here');
});

test('A trial with no posted results says that, rather than showing nothing', () => {
  const html = trialResultsView({summary: {nct_id: 'NCT04708782', has_results: false}});
  assert.match(html, /결과를 게시하지 않았습니다/);
  assert.match(html, /효과 없음과 다릅니다/, 'not posted is not the same as no effect');
  assert.match(html, /href="https:\/\/clinicaltrials\.gov\/study\/NCT04708782"/);
});

test('A missing measurement is reported as missing and never filled in', () => {
  const value = withResults();
  value.response.resultsSection.outcomeMeasuresModule.outcomeMeasures[0]
    .classes[0].categories[0].measurements = [{groupId: 'OG000', value: ''}];
  const html = trialResultsView(value);
  assert.match(html, /미보고/);
  assert.doesNotMatch(html, /-183\.48/);
});

test('The paged view reads the derived block and states the full event totals', () => {
  const full = withResults().response.resultsSection;
  const paged = {summary: {nct_id: 'NCT05321069', has_results: true},
    reported_results: {
      outcomeMeasures: full.outcomeMeasuresModule.outcomeMeasures,
      adverseEvents: {...full.adverseEventsModule, seriousEventsTotal: 359, otherEventsTotal: 21,
                      seriousEvents: full.adverseEventsModule.seriousEvents,
                      otherEvents: full.adverseEventsModule.otherEvents},
      shown_events_per_list: 12}};
  const html = trialResultsView(paged);
  assert.match(html, /-114\.65/, 'the same outcome renders without the raw response');
  assert.match(html, /중대한 이상반응 359건 중 빈도 상위 1건/,
               'the truncated list still states how many were reported');
  assert.match(html, /기타 이상반응 21건 중 빈도 상위 1건/);
});

test('Values from the record cannot inject markup', () => {
  const value = withResults();
  value.response.resultsSection.outcomeMeasuresModule.outcomeMeasures[0].title = '<img src=x>';
  const html = trialResultsView(value);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});
