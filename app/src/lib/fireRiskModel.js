import model from '../data/fireRiskModel.json';

function sigmoid(z) {
  return 1 / (1 + Math.exp(-z));
}

// weather: { temp_max, temp_min, wind_max, precip_sum, humidity_mean }
export function predictRisk(weather) {
  const x = model.features.map((f) => weather[f]);
  const z = x.reduce((sum, xi, i) => {
    const normalized = (xi - model.mean[i]) / model.std[i];
    return sum + normalized * model.coef[i];
  }, model.intercept);
  return sigmoid(z);
}

export function riskLevel(score) {
  if (score >= 0.75) return { label: 'Extreme', color: '#a8481f' };
  if (score >= 0.5) return { label: 'High', color: '#e8622c' };
  if (score >= 0.25) return { label: 'Moderate', color: '#f0a34a' };
  return { label: 'Low', color: '#ffd9a0' };
}

export const modelInfo = model.trained_on;
