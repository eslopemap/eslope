const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, 'colorpickerlist.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const start = html.indexOf('class Hsluv');
const end = html.indexOf('let colors');
if (start < 0 || end < 0 || end <= start) {
  throw new Error('Could not locate Hsluv/ColorConvert snippet in colorpickerlist.html');
}

const snippet = html.slice(start, end);

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

const { ColorConvert } = (new Function(`${snippet}; return { ColorConvert };`))();

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
