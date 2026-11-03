import {recommend, selectHours, description, sampleWeather} from './outfit-engine.mjs';
import {avatarSVG, palettes} from './avatar.mjs';
const $ = id => document.getElementById(id);
const defaults = {skin:'warm',hair:'short',hairColor:'dark',frame:'regular',height:175};
function read(key, fallback) {try {return JSON.parse(localStorage.getItem(key)) ?? fallback;} catch {return fallback;}}
function save(key,value) {try {localStorage.setItem(key,JSON.stringify(value));return true;} catch {return false;}}
function validPrefs(raw) {
  const p = {...defaults};
  for (const [key,allowed] of Object.entries({skin:['light','sand','warm','brown','deep'],hair:['short','bob','long','cropped'],hairColor:['dark','brown','blonde','silver'],frame:['slim','regular','broad']})) if (allowed.includes(raw?.[key])) p[key] = raw[key];
  if (Number.isFinite(Number(raw?.height))) p.height = Math.max(140,Math.min(210,Number(raw.height)));
  return p;
}
let prefs = validPrefs(read('wa-avatar',defaults));
let weather = sampleWeather(), period = 'day', comfort = 'balanced', activity = 'everyday', unit = 'C', paletteIndex = 0;
let locationName = 'Explore a sample day', controller;
const settings=read('wa-daily-settings',{});
if(['cold','balanced','warm'].includes(settings.comfort)) comfort=settings.comfort;
if(['everyday','work','walking'].includes(settings.activity)) activity=settings.activity;
if(['C','F'].includes(settings.unit)) unit=settings.unit;
if(Number.isInteger(settings.paletteIndex) && settings.paletteIndex >= 0 && settings.paletteIndex < palettes.length) paletteIndex=settings.paletteIndex;
$('activity').value=activity;
function saveSettings(){save('wa-daily-settings',{comfort,activity,unit,paletteIndex});}
const periods = {day:['Next 12 hours','From now, including overnight'],morning:['Morning','06:00 – 12:00'],afternoon:['Afternoon','12:00 – 18:00'],evening:['Evening','18:00 – 00:00']};
const temp = n => Math.round(unit === 'F' ? n*9/5+32 : n) + '°';
const text = (id,value) => {$(id).textContent=value;};
const icon = code => code >= 95 ? 'ϟ' : [71,73,75,77,85,86].includes(code) ? '❄' : code >= 51 ? '☂' : code >= 2 ? '☁' : '☀';
function garmentIcon(type, color, outfit) {
  const paths = {layer:'M15 9L7 13 3 33 10 35 15 23 14 46 26 46 26 14 23 9 M29 9L32 14 32 46 44 46 43 23 48 35 55 33 47 13 39 9 34 14 28 14Z',top:'M19 10L8 15 3 28 13 33 17 26 17 46 43 46 43 26 47 33 57 28 52 15 41 10Q30 21 19 10Z',bottom:outfit.bottom === 'shorts'?'M16 12H44L48 42H33L30 27 27 42H12Z':'M16 7H44L47 51H33L30 23 27 51H13Z',shoes:'M11 25L22 24 28 35 47 39Q54 42 49 47H7Q4 45 7 38Z'};
  return `<svg viewBox="0 0 60 60" aria-hidden="true"><path d="${paths[type]}" fill="${color}" stroke="#26332d" stroke-opacity=".25" stroke-width="1.3"/>${type === 'layer'?'<path d="M18 24h5m13 0h5" stroke="#fff" opacity=".5"/>':''}</svg>`;
}
function render() {
  saveSettings();
  let hours = selectHours(weather,period);
  if (!hours.length) {period='day';hours=selectHours(weather,period);}
  if (!hours.length) {text('status','This forecast is no longer current. Choose your location to refresh it.');return;}
  const outfit = recommend(hours,{comfort,activity}), palette = palettes[paletteIndex];
  text('temperature',temp(weather.current.temp));text('condition',description(weather.current.code));
  text('feels-like',`Feels like ${temp(weather.current.feels)} · ${unit === 'C' ? 'Celsius' : 'Fahrenheit'}`);
  text('weather-symbol',icon(weather.current.code));text('high-low',`${temp(weather.high)} / ${temp(weather.low)}`);
  text('rain-value',`${outfit.rain}%`);text('wind-value',`${Math.round(outfit.wind)} km/h`);
  text('weather-footnote','Rain and wind: maximum in your selected hours.');
  text('weather-label',weather.source === 'sample' ? 'SAMPLE DAY' : 'CURRENT WEATHER');
  text('location-name',locationName);text('source-badge',weather.source === 'sample' ? 'SAMPLE WEATHER · NOT YOUR LOCATION' : `LIVE FORECAST · UPDATED ${weather.time.slice(11,16)}`);
  text('forecast-zone',weather.source === 'sample' ? 'Sample forecast' : `${weather.time.slice(0,10)} · ${weather.timezone.replaceAll('_',' ')}`);
  text('outfit-title',outfit.title);
  text('outfit-summary',`For ${activity === 'work' ? 'your workday' : activity === 'walking' ? 'a walk outside' : 'whatever the day brings'}. Feels like ${temp(outfit.min)}–${temp(outfit.max)} during these hours.`);
  $('avatar').innerHTML = avatarSVG(outfit,prefs,palette);
  $('avatar').setAttribute('aria-label',`Full-body illustrated avatar wearing ${outfit.items.map(i=>i.name.toLowerCase()).join(', ')}.`);
  text('palette-name',palette.name);text('outfit-callout',outfit.wet ? 'A little rain.\nStill your day.' : outfit.layer === 'coat' ? 'Warm layers.\nGood company.' : 'Made for a little\nof everything.');
  $('items').replaceChildren();
  for (const item of outfit.items) {
    const div = document.createElement('article');div.className='outfit-item';
    const pic = document.createElement('div');pic.className='item-icon';
    const color = {layer:palette.outer,top:palette.top,bottom:palette.bottom,shoes:outfit.shoes==='boots'?'#574c40':palette.shoe}[item.type];
    pic.innerHTML=garmentIcon(item.type,color,outfit);
    const copy=document.createElement('div'),h=document.createElement('h3'),p=document.createElement('p');
    h.textContent=item.name;p.textContent=item.note;copy.append(h,p);div.append(pic,copy);$('items').append(div);
  }
  text('reason',outfit.reasons.join(' '));text('warning',outfit.warning);$('warning').hidden=!outfit.warning;
  $('periods').replaceChildren();
  for (const [key,[name,range]] of Object.entries(periods)) {
    const hs=selectHours(weather,key), b=document.createElement('button');b.className='period';b.disabled=!hs.length;b.setAttribute('aria-pressed',String(period===key));
    const left=document.createElement('span'), label=document.createElement('strong'), sub=document.createElement('small'), right=document.createElement('span');
    label.textContent=name;sub.textContent=hs.length ? range : 'Earlier today';left.append(label,sub);right.className='period-temp';right.textContent=hs.length?temp(Math.min(...hs.map(h=>h.feels))):'—';
    b.append(left,right);b.addEventListener('click',()=>{period=key;render();});$('periods').append(b);
  }
  document.querySelectorAll('[data-comfort]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.comfort===comfort)));
  $('unit').setAttribute('aria-label',`Switch to ${unit==='C'?'Fahrenheit':'Celsius'}`);
}
// Dialogs keep native focus trapping and Escape support. Changes preview live;
// cancel restores the saved appearance, while Save explicitly persists it.
let beforeEdit;
document.querySelectorAll('[data-open]').forEach(b=>b.addEventListener('click',()=>{
  if (b.dataset.open==='avatar-dialog') {
    beforeEdit={...prefs};
    for(const [id,key] of [['skin','skin'],['hair','hair'],['hair-color','hairColor'],['frame','frame'],['height','height']]) $(id).value=prefs[key];
    text('height-value',`${prefs.height} cm`);
  }
  $(b.dataset.open).showModal();
}));
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
$('avatar-dialog').addEventListener('close',()=>{if(beforeEdit){prefs=beforeEdit;beforeEdit=null;render();}});
$('avatar-form').addEventListener('input',()=>{prefs=validPrefs({skin:$('skin').value,hair:$('hair').value,hairColor:$('hair-color').value,frame:$('frame').value,height:Number($('height').value)});text('height-value',`${prefs.height} cm`);render();});
$('avatar-form').addEventListener('submit',e=>{e.preventDefault();const persisted=save('wa-avatar',prefs);beforeEdit=null;$('avatar-dialog').close();text('status',persisted?'Your avatar is saved in this browser.':'Your avatar is updated for this visit. Browser storage is unavailable.');});
$('activity').addEventListener('change',()=>{activity=$('activity').value;render();});
document.querySelectorAll('[data-comfort]').forEach(b=>b.addEventListener('click',()=>{comfort=b.dataset.comfort;render();}));
$('unit').addEventListener('click',()=>{unit=unit==='C'?'F':'C';render();});
$('shuffle').addEventListener('click',()=>{paletteIndex=(paletteIndex+1)%palettes.length;render();});
$('sample').addEventListener('change',()=>{controller?.abort();weather=sampleWeather($('sample').value);locationName='Explore a sample day';period='day';text('status','You’re viewing sample weather. Choose a location for your forecast.');render();});
async function json(url,signal) {const response=await fetch(url,{signal});const data=await response.json();if(!response.ok)throw new Error(data.error || 'Something went wrong. Please try again.');return data;}
async function loadLocation(place) {
  controller?.abort();const requestController=new AbortController();controller=requestController;
  text('search-status','Getting your forecast…');text('status','Getting your forecast…');
  try {
    const data=await json(`/api/daily-weather?lat=${encodeURIComponent(place.latitude)}&lon=${encodeURIComponent(place.longitude)}`,requestController.signal);
    weather=data;locationName=place.name;period='day';save('wa-location',place);$('sample').value='';render();$('location-dialog').close();text('status','');text('search-status','');
  } catch(error) {if(error.name!=='AbortError'){text('search-status',error.message);text('status',error.message);}}
}
let searchController;
$('search-form').addEventListener('submit',async e=>{
  e.preventDefault();searchController?.abort();searchController=new AbortController();
  text('search-status','Finding your city…');$('locations').replaceChildren();
  try {
    const data=await json(`/api/locations?q=${encodeURIComponent($('city').value.trim())}`,searchController.signal);
    text('search-status',data.locations.length?'Choose your location.':'No places found. Try a nearby city or add a country.');
    for(const place of data.locations){const b=document.createElement('button');b.type='button';b.className='location-result';b.textContent=place.name;b.addEventListener('click',()=>loadLocation(place));$('locations').append(b);}
  } catch(error) {if(error.name!=='AbortError')text('search-status',error.message);}
});
$('geolocate').addEventListener('click',()=>{
  if(!navigator.geolocation){text('search-status','Location is not supported here. Search by city instead.');return;}
  text('search-status','Waiting for your location…');$('geolocate').disabled=true;
  navigator.geolocation.getCurrentPosition(pos=>{ $('geolocate').disabled=false;loadLocation({latitude:pos.coords.latitude,longitude:pos.coords.longitude,name:'Current location'});},()=>{$('geolocate').disabled=false;text('search-status','Location was unavailable or not allowed. Search by city instead.');},{timeout:10000,maximumAge:300000});
});
render();
const savedLocation=read('wa-location',null);
if(savedLocation && typeof savedLocation.name==='string' && Number.isFinite(savedLocation.latitude) && Number.isFinite(savedLocation.longitude)) loadLocation(savedLocation);
