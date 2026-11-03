// All temperatures are Celsius and winds km/h. Apparent temperature already
// accounts for wind/humidity; wind separately controls the protective layer.
export function recommend(hours, {comfort = 'balanced', activity = 'everyday'} = {}) {
  const offset = {cold: -3, balanced: 0, warm: 3}[comfort] ?? 0;
  const min = Math.min(...hours.map(h => h.feels));
  const max = Math.max(...hours.map(h => h.feels));
  const effective = min + offset + (activity === 'walking' ? 2 : 0);
  const rain = Math.max(...hours.map(h => h.rain));
  const wind = Math.max(...hours.map(h => h.wind));
  const snow = hours.some(h => [71,73,75,77,85,86].includes(h.code));
  const wet = rain >= 40 || hours.some(h => (h.code >= 51 && h.code <= 67) || h.code >= 80);
  const cold = effective < 10;
  const hot = effective >= 25;
  const layer = cold ? 'coat' : wet ? 'raincoat' : effective < 18 || wind >= 25 ? 'jacket' : 'none';
  const top = effective < 14 ? 'knit' : activity === 'work' ? 'shirt' : 'tee';
  const bottom = hot && activity !== 'work' ? 'shorts' : 'trousers';
  const shoes = wet || snow ? 'boots' : 'sneakers';
  const titles = {coat: 'A little extra warmth.', raincoat: 'Ready for a change of weather.', jacket: 'Light layers. Easy day.', none: hot ? 'Keep it light. Stay cool.' : 'Comfort, without the layers.'};
  const items = [
    {type: 'top', name: {knit: 'Fine-knit sweater', shirt: 'Cotton button-down', tee: 'Breathable cotton tee'}[top], note: top === 'knit' ? 'A soft layer to hold warmth.' : 'An easy, breathable base.'},
    {type: 'bottom', name: bottom === 'shorts' ? 'Relaxed shorts' : activity === 'work' ? 'Tailored trousers' : 'Relaxed cotton trousers', note: bottom === 'shorts' ? 'Less coverage for warm weather.' : 'Comfortable coverage throughout the day.'},
    {type: 'shoes', name: shoes === 'boots' ? 'Weather-resistant boots' : 'Everyday sneakers', note: shoes === 'boots' ? 'Choose grippy soles for wet ground.' : 'Comfort for time on your feet.'},
  ];
  if (layer !== 'none') items.unshift({type: 'layer', name: {coat: wet || snow ? 'Water-resistant insulated coat' : 'Insulated coat', raincoat: 'Lightweight rain jacket', jacket: 'Lightweight overshirt'}[layer], note: layer === 'raincoat' ? 'A packable shell for passing showers.' : layer === 'coat' ? 'Insulation for colder hours.' : 'Easy to take off when it warms up.'});
  const reasons = [cold ? 'Insulation for the colder hours.' : hot ? 'Light fabrics help release heat.' : layer !== 'none' ? 'A removable layer gives you flexibility.' : 'Breathable basics suit these conditions.'];
  if (wet) reasons.push('Rain is possible: choose a water-resistant outer layer and footwear.');
  if (wind >= 25) reasons.push('A closed outer layer helps block the wind.');
  if (max - min >= 7) reasons.push('Temperatures change noticeably; remove your outer layer as it warms up.');
  if (comfort !== 'balanced') reasons.push(comfort === 'cold' ? 'Adjusted for your preference for extra warmth.' : 'Adjusted for your preference for lighter clothing.');
  if (activity === 'walking') reasons.push('Adjusted for the warmth you build up walking.');
  const warning = hours.some(h => h.code >= 95) ? 'Thunderstorms possible. Check local alerts before heading out.' : min <= -10 || max >= 38 ? 'Extreme temperatures: check local guidance and limit exposure.' : wind >= 60 ? 'Strong winds expected. Check local weather alerts.' : '';
  return {layer, top, bottom, shoes, title: titles[layer], items, reasons, min, max, rain, wind, wet, snow, warning};
}
export function selectHours(weather, period) {
  const now = weather.time;
  const day = now.slice(0, 10);
  const bands = {morning: [6, 12], afternoon: [12, 18], evening: [18, 24]};
  const available = weather.hours.filter(h => h.time >= now.slice(0, 13) + ':00');
  if (period === 'day') return available.slice(0, 12);
  const [start, end] = bands[period];
  return available.filter(h => h.time.startsWith(day) && Number(h.time.slice(11,13)) >= start && Number(h.time.slice(11,13)) < end);
}
export function description(code) {
  if (code >= 95) return 'Thunderstorms';
  if ([71,73,75,77,85,86].includes(code)) return 'Snow';
  if (code >= 51) return 'Showers';
  if (code >= 45) return 'Foggy';
  return ['Clear skies', 'Mostly clear', 'Partly cloudy', 'Overcast'][code] || 'Cloudy';
}
export function sampleWeather(kind = 'mild') {
  const presets = {mild:[18,23,17,15,16], rain:[14,17,13,75,28], hot:[28,33,27,5,10], cold:[0,5,-2,30,22]};
  const [am,pm,night,rain,wind] = presets[kind] || presets.mild;
  const hours = Array.from({length: 42}, (_,i) => {
    const hour = (i + 6) % 24, day = i + 6 < 24 ? '27' : '28';
    const temp = hour < 12 ? am : hour < 18 ? pm : night;
    return {time:`2026-10-${day}T${String(hour).padStart(2,'0')}:00`, temp, feels: temp - (kind === 'cold' ? 3 : 1), rain: hour >= 15 ? rain : Math.max(0,rain-15), wind, code:kind === 'rain' ? 61 : kind === 'hot' ? 0 : 2};
  });
  return {source:'sample',time:'2026-10-27T08:00',timezone:'Sample forecast',current:hours[2],high:pm,low:night,hours};
}
