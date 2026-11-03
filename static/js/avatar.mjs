const skins = {light:['#f1c9b1','#dca488'],sand:['#d9a080','#b87a5b'],warm:['#b87c58','#905438'],brown:['#8b573c','#643b2a'],deep:['#593a2d','#38251f']};
const hairs = {dark:'#2a2927',brown:'#62402e',blonde:'#b79258',silver:'#a5a4a0'};
export const palettes = [
  {name:'Earth & sky',outer:'#77877b',top:'#f0ece1',bottom:'#353f48',shoe:'#eee9de'},
  {name:'Sand & stone',outer:'#b69474',top:'#faf4e5',bottom:'#555c58',shoe:'#f5eee0'},
  {name:'Midnight & cream',outer:'#3e536c',top:'#e7dbbf',bottom:'#b6a589',shoe:'#e5e4de'},
  {name:'Clay & charcoal',outer:'#b77157',top:'#f2e9d9',bottom:'#41434a',shoe:'#e5ded4'},
];
export function avatarSVG(outfit, prefs, palette) {
  const [skin, shade] = skins[prefs.skin] || skins.warm;
  const hair = hairs[prefs.hairColor] || hairs.dark;
  const width = {slim:.91, regular:1, broad:1.13}[prefs.frame] || 1;
  const height = Math.max(.85, Math.min(1.06, Number(prefs.height)/180 || .97));
  const shorts = outfit.bottom === 'shorts';
  const coat = outfit.layer === 'coat';
  const longSleeves = outfit.top !== 'tee';
  const outer = outfit.layer !== 'none';
  const boots = outfit.shoes === 'boots';
  return `<svg viewBox="0 0 400 620" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <defs>
    <linearGradient id="skin-shade" x1="0" x2="1"><stop stop-color="${shade}"/><stop offset=".45" stop-color="${skin}"/><stop offset="1" stop-color="${skin}"/></linearGradient>
    <linearGradient id="cloth" x1="0" x2="1"><stop stop-color="#000" stop-opacity=".18"/><stop offset=".3" stop-color="#fff" stop-opacity=".05"/><stop offset=".7" stop-color="#fff" stop-opacity=".02"/><stop offset="1" stop-color="#000" stop-opacity=".16"/></linearGradient>
    <filter id="shadow"><feGaussianBlur stdDeviation="6"/></filter>
  </defs>
  <ellipse cx="200" cy="583" rx="75" ry="9" fill="#423d32" opacity=".15" filter="url(#shadow)"/>
  <g transform="translate(200 580) scale(${width} ${height}) translate(-200 -580)" stroke-linecap="round" stroke-linejoin="round">
  ${['long','bob'].includes(prefs.hair) ? `<path d="M163 75 Q157 36 197 34 Q241 32 242 80 L${prefs.hair === 'long' ? '254 197 Q228 215 218 187 L175 183 Q147 200 145 173' : '244 122 Q232 138 214 124 L174 128 Q150 131 154 111'}Z" fill="${hair}"/>` : ''}
  <!-- Neck, ears, and face -->
  <path d="M184 101 L182 129 Q168 135 166 140 Q200 162 233 139 L217 128 L215 98Z" fill="url(#skin-shade)"/>
  <path d="M184 104 Q202 119 215 99 L215 118 Q202 129 184 118Z" fill="${shade}" opacity=".48"/>
  <ellipse cx="166" cy="82" rx="6" ry="10" fill="${skin}"/><ellipse cx="232" cy="82" rx="6" ry="10" fill="${skin}"/>
  <path d="M167 64 Q167 38 199 38 Q231 38 232 68 L228 94 Q223 109 203 117 Q184 114 173 99Z" fill="url(#skin-shade)"/>
  <path d="M177 76 Q184 72 190 75 M209 75 Q216 72 223 76" fill="none" stroke="${hair}" stroke-width="2.8"/>
  <path d="M178 81 Q184 78 190 81 M209 81 Q216 78 222 81" fill="none" stroke="#352b28" stroke-width="1.4"/>
  <ellipse cx="185" cy="81.5" rx="1.7" ry="2" fill="#272626"/><ellipse cx="215" cy="81.5" rx="1.7" ry="2" fill="#272626"/>
  <path d="M201 80 L198 92 Q201 94 205 92" fill="none" stroke="${shade}" stroke-width="1.5"/>
  <path d="M191 101 Q201 106 211 100" fill="none" stroke="#835342" stroke-width="1.6"/><path d="M197 106 L205 106" stroke="${skin}" stroke-width="1.2"/>
  ${prefs.hair === 'cropped' ? `<path d="M168 71 L166 61 Q170 34 200 35 Q229 36 233 62 L231 72 L225 55 Q196 47 175 57Z" fill="${hair}"/>` : prefs.hair === 'short' ? `<path d="M168 78 Q160 67 163 54 Q157 48 165 42 Q166 28 181 30 Q189 18 203 26 Q222 20 229 34 Q244 42 236 58 L232 77 L225 60 L223 48 Q204 62 177 54 L173 76Z" fill="${hair}"/><path d="M177 43 Q194 31 215 37 M181 48 Q199 39 220 42" fill="none" stroke="#fff" opacity=".09" stroke-width="2"/>` : `<path d="M166 78 Q158 46 182 36 Q210 22 230 47 L234 80 Q221 68 215 50 Q198 67 174 62 L172 82Z" fill="${hair}"/>`}
  <!-- Legs and relaxed tailored trousers -->
  <path d="M155 291 L199 300 L192 435 L183 553 L158 553 L156 437Z M200 299 L244 292 L241 437 L244 551 L220 554 L204 438Z" fill="url(#skin-shade)"/>
  <path d="M153 284 Q198 298 246 282 L244 ${shorts?'392':'540'} L216 ${shorts?'393':'542'} L199 ${shorts?'338':'372'} L188 ${shorts?'393':'543'} L156 ${shorts?'391':'541'}Z" fill="${palette.bottom}"/>
  <path d="M153 284 Q198 298 246 282 L244 ${shorts?'392':'540'} L216 ${shorts?'393':'542'} L199 ${shorts?'338':'372'} L188 ${shorts?'393':'543'} L156 ${shorts?'391':'541'}Z" fill="url(#cloth)"/>
  <path d="M199 301 L199 337 M157 315 Q173 320 178 297 M224 297 Q225 319 241 321 M172 347 L169 ${shorts?'381':'524'} M228 346 L232 ${shorts?'382':'524'}" fill="none" stroke="#000" stroke-opacity=".12" stroke-width="1.4"/>
  <path d="M156 ${shorts?'386':'535'} L188 ${shorts?'388':'538'} M217 ${shorts?'388':'537'} L243 ${shorts?'387':'535'}" stroke="#fff" stroke-opacity=".13" stroke-width="2"/>
  <!-- Footwear -->
  <path d="M158 ${boots?'528':'550'} L183 ${boots?'528':'550'} L185 564 Q186 576 178 580 L139 580 Q131 577 136 569 L156 560Z M218 ${boots?'528':'550'} L242 ${boots?'528':'550'} L246 562 L267 572 Q272 580 264 582 L223 582 Q216 578 217 568Z" fill="${boots?'#574c40':palette.shoe}" stroke="#49453d" stroke-width="1"/>
  <path d="M136 576 Q159 580 184 575 M219 577 Q245 581 267 577" fill="none" stroke="${boots?'#332e28':'#c9c6ba'}" stroke-width="4"/>
  <path d="M157 564 L174 565 M152 569 L170 569 M227 565 L242 563 M232 570 L248 568" stroke="${boots?'#a5957b':'#a3a39b'}" stroke-width="1.7"/>
  <!-- Arms / hands -->
  <path d="M148 149 Q133 149 127 175 L110 256 L105 307 Q100 319 104 331 Q108 338 111 332 L113 318 L116 332 Q121 336 123 328 L125 310 L129 260 L151 192Z" fill="url(#skin-shade)"/>
  <path d="M248 149 Q265 147 272 175 L286 253 L294 304 Q302 314 298 328 Q294 335 291 329 L287 315 L287 332 Q282 335 278 325 L277 308 L269 260 L248 190Z" fill="url(#skin-shade)"/>
  <!-- Base top -->
  <path d="M182 127 Q200 145 218 127 L251 139 Q265 147 268 167 L${longSleeves?'285 286 L268 291 L249 200':'270 193 L248 199 L246 179'} L245 290 Q201 301 154 290 L153 185 L${longSleeves?'130 289 L110 284 L127 167':'150 200 L125 193 L130 166'} Q132 148 147 140Z" fill="${palette.top}"/>
  <path d="M182 127 Q200 145 218 127 L251 139 Q265 147 268 167 L${longSleeves?'285 286 L268 291 L249 200':'270 193 L248 199 L246 179'} L245 290 Q201 301 154 290 L153 185 L${longSleeves?'130 289 L110 284 L127 167':'150 200 L125 193 L130 166'} Q132 148 147 140Z" fill="url(#cloth)"/>
  <path d="M182 131 Q200 150 219 131 M161 280 Q196 289 237 280 M153 179 L158 212 M245 179 L239 211" fill="none" stroke="#000" opacity=".12" stroke-width="2"/>
  ${outfit.top === 'shirt' ? `<path d="M181 128 L199 142 L190 160 L176 135 M218 128 L199 142 L208 160 L225 135 M199 145 L199 289" fill="none" stroke="#999084" stroke-width="1.5"/><g fill="#908b82">${[171,197,224,250,277].map(y=>`<circle cx="203" cy="${y}" r="1.5"/>`).join('')}</g>` : ''}
  ${outer ? `<path d="M179 127 L145 139 Q132 143 128 165 L106 281 L129 289 L153 192 L151 ${coat?'352':'294'} Q174 ${coat?'358':'301'} 192 ${coat?'352':'294'} L187 170Z M221 127 L253 139 Q267 144 272 168 L291 281 L268 290 L246 191 L249 ${coat?'352':'294'} Q226 ${coat?'359':'303'} 208 ${coat?'352':'294'} L211 169Z" fill="${palette.outer}" stroke="#000" stroke-opacity=".1"/>
  <path d="M179 127 L145 139 Q132 143 128 165 L106 281 L129 289 L153 192 L151 ${coat?'352':'294'} Q174 ${coat?'358':'301'} 192 ${coat?'352':'294'} L187 170Z M221 127 L253 139 Q267 144 272 168 L291 281 L268 290 L246 191 L249 ${coat?'352':'294'} Q226 ${coat?'359':'303'} 208 ${coat?'352':'294'} L211 169Z" fill="url(#cloth)"/>
  <path d="M179 127 L168 146 L190 179 L185 143 M221 127 L232 146 L210 179 L215 144" fill="${palette.outer}" stroke="#000" stroke-opacity=".18" stroke-width="1.5"/>
  <path d="M158 204 L183 204 L181 226 Q170 232 159 225Z M219 204 L242 204 L241 226 Q229 232 219 225Z" fill="#000" fill-opacity=".035" stroke="#000" stroke-opacity=".18"/>
  <path d="M111 273 L130 278 M269 279 L288 273 M153 ${coat?'342':'286'} L188 ${coat?'346':'290'} M211 ${coat?'346':'290'} L247 ${coat?'342':'286'}" stroke="#000" stroke-opacity=".2" fill="none" stroke-width="2"/>
  <g fill="#dcd9cc">${[190,236,278,...(coat?[320]:[])].map(y=>`<circle cx="216" cy="${y}" r="2"/>`).join('')}</g>
  ${outfit.layer === 'raincoat' || (coat && outfit.wet) ? `<path d="M178 125 Q150 107 162 96 Q171 92 179 110 M221 125 Q247 108 237 96 Q230 92 221 110" fill="${palette.outer}" stroke="#000" stroke-opacity=".15" stroke-width="2"/><path d="M187 151 L184 184 M213 151 L216 184" stroke="#d9d6c9" stroke-width="2"/>` : ''}` : ''}
  ${coat ? `<path d="M181 124 Q199 137 219 124 L220 148 Q201 157 179 144Z" fill="${palette.top}"/><path d="M208 147 L218 205 L204 210 L197 149" fill="${palette.top}"/><path d="M207 203 L216 201" stroke="#000" stroke-opacity=".15"/>` : ''}
  </g></svg>`;
}
