import test from 'node:test';
import assert from 'node:assert/strict';
import { weatherScene } from '../static/js/weather-scene.mjs';
test('all provider WMO conditions receive an appropriate current scene',()=>{
  const groups={clear:[0],'partly-cloudy':[1,2],cloudy:[3],fog:[45,48],rain:[51,53,55,56,57,61,63,65,66,67,80,81,82],snow:[71,73,75,77,85,86],storm:[95,96,99]};
  for(const [scene,codes]of Object.entries(groups))for(const code of codes)assert.equal(weatherScene(code,true),scene,`WMO ${code}`);
});
test('night skies change while precipitation remains recognizable at night',()=>{
  assert.equal(weatherScene(0,false),'night-clear');
  for(const code of [1,2,3])assert.equal(weatherScene(code,0),'night-cloudy');
  for(const code of [45,61,75,95])assert.equal(weatherScene(code,false),weatherScene(code,true));
});
test('missing and unfamiliar codes do not imply clear weather',()=>{
  for(const code of [null,undefined,NaN,'0',-1,100])assert.equal(weatherScene(code,true),'unknown');
});
