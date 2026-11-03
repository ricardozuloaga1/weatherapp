// Use current WMO conditions, never upcoming rain or the outfit recommendation.
export function weatherScene(code, isDay) {
  const night = isDay === false || isDay === 0;
  if ([95, 96, 99].includes(code)) return 'storm';
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'snow';
  if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return 'rain';
  if ([45, 48].includes(code)) return 'fog';
  if (code === 0) return night ? 'night-clear' : 'clear';
  if ([1, 2].includes(code)) return night ? 'night-cloudy' : 'partly-cloudy';
  if (code === 3) return night ? 'night-cloudy' : 'cloudy';
  return 'unknown';
}
