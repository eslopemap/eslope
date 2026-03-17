const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, 'colorpickerlist.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const scriptStart = html.indexOf('<script>');
const scriptEnd = html.indexOf('</script>');
if (scriptStart < 0 || scriptEnd < 0 || scriptEnd <= scriptStart) {
  throw new Error('Could not locate <script> block in colorpickerlist.html');
}
const script = html.slice(scriptStart + '<script>'.length, scriptEnd);

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function assertNear(actual, expected, eps, msg) {
  if (Math.abs(actual - expected) > eps) {
    throw new Error(`${msg}: expected ${expected} ± ${eps}, got ${actual}`);
  }
}

function assertRgbEq(actual, expected, msg) {
  assert(Array.isArray(actual) && actual.length === 3, `${msg}: not an RGB triplet`);
  for (let i = 0; i < 3; i++) {
    if (actual[i] !== expected[i]) {
      throw new Error(`${msg}: expected [${expected}], got [${actual}]`);
    }
  }
}

// For Node tests we must NOT evaluate UI code (it needs a browser DOM).
// Extract only the conversion + closest-name helpers and the colornames map.
const start = script.indexOf('class Hsluv');
const end = script.indexOf('function addColor');
if (start < 0 || end < 0 || end <= start) {
  throw new Error('Could not locate Hsluv/ColorConvert/closestColorName snippet in colorpickerlist.html');
}
const coreSnippet = script.slice(start, end);

const namesStart = script.indexOf('globalThis.colornames = {');
if (namesStart < 0) {
  throw new Error('Could not locate globalThis.colornames in colorpickerlist.html');
}
const namesEnd = script.indexOf('};', namesStart);
if (namesEnd < 0) {
  throw new Error('Could not locate end of globalThis.colornames object');
}
const namesSnippet = script.slice(namesStart, namesEnd + 2);

const { ColorConvert, closestColorName } = (new Function(`
const window = { addEventListener: () => {} };
const sessionStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};
${coreSnippet}
${namesSnippet}
return { ColorConvert, closestColorName };`))();

// 1) Roundtrip red
const hsluvRed = ColorConvert.rgbToHsluv(255, 0, 0);
const rgbRed2 = ColorConvert.hsluvToRgb(hsluvRed[0], hsluvRed[1], hsluvRed[2]);
assertRgbEq(rgbRed2, [255, 0, 0], 'red roundtrip');

// 2) White and black invariants
const hsluvWhite = ColorConvert.rgbToHsluv(255, 255, 255);
assertNear(hsluvWhite[1], 0, 1e-9, 'white saturation');
assertNear(hsluvWhite[2], 100, 1e-9, 'white lightness');
assertRgbEq(ColorConvert.hsluvToRgb(0, 0, 100), [255, 255, 255], 'hsluv(0,0,100)');

const hsluvBlack = ColorConvert.rgbToHsluv(0, 0, 0);
assertNear(hsluvBlack[1], 0, 1e-9, 'black saturation');
assertNear(hsluvBlack[2], 0, 1e-9, 'black lightness');
assertRgbEq(ColorConvert.hsluvToRgb(0, 0, 0), [0, 0, 0], 'hsluv(0,0,0)');

// 3) A known-ish numeric check (tolerant): red hue/lightness
// Values taken from sanity check when wiring the implementation.
assertNear(hsluvRed[0], 12.177050630061776, 1e-6, 'red hue');
assertNear(hsluvRed[2], 53.23711559542933, 1e-6, 'red lightness');

console.log('OK: colorpickerlist.html HSLuv tests passed');

// 4) Closest XKCD name tests
// These should exist in the XKCD list appended at the end of the HTML.
assert(closestColorName([255, 0, 0]).length > 0, 'closestColorName red should not be empty');
assert(closestColorName([0, 255, 0]).length > 0, 'closestColorName green should not be empty');
assert(closestColorName([0, 0, 255]).length > 0, 'closestColorName blue should not be empty');

// canonical exact entries (from the provided list)
assert(closestColorName([255, 0, 0]) === 'red', 'closestColorName([255,0,0])');
assert(closestColorName([0, 255, 0]) === 'green', 'closestColorName([0,255,0])');
assert(closestColorName([0, 0, 255]) === 'blue', 'closestColorName([0,0,255])');

console.log('OK: closestColorName tests passed');
