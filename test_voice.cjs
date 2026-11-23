const {test} = require('node:test');
const assert = require('node:assert/strict');
const {VoiceChat} = require('./public/voice.js');

function setup() {
  const recognizers = [], spoken = [], sent = [];
  class Recognition {
    constructor() { recognizers.push(this); }
    start() { this.onstart(); }
    abort() { this.aborted = true; }
  }
  const speech = {cancel() {}, getVoices: () => [], speak: u => spoken.push(u)};
  const voice = new VoiceChat({Recognition, speech, Utterance: class {}, lang: 'en-IN',
    onState() {}, onTranscript: text => sent.push(text)});
  return {voice, recognizers, spoken, sent};
}
test('only final transcripts submit; microphone stays off during reply and speech', () => {
  const {voice, recognizers, spoken, sent} = setup();
  voice.start(true);
  const recognition = recognizers[0];
  recognition.onresult({results: [Object.assign([{transcript: 'hello'}], {isFinal: false})]});
  assert.deepEqual(sent, []);
  recognition.onresult({results: [Object.assign([{transcript: 'hello world'}], {isFinal: true})]});
  recognition.onend();
  assert.deepEqual(sent, ['hello world']);
  assert.equal(recognizers.length, 1);
  voice.reply('Hello back');
  assert.equal(spoken[0].text, 'Hello back');
  assert.equal(recognizers.length, 1);
  spoken[0].onend();
  assert.equal(recognizers.length, 2);
  voice.stop();
  recognizers[1].onend();
  assert.equal(recognizers.length, 2);
});
test('permission failures stop voice mode and stale callbacks cannot send', () => {
  const {voice, recognizers, sent} = setup();
  voice.start(true);
  recognizers[0].onerror({error: 'not-allowed'});
  assert.equal(voice.active, false);
  recognizers[0].onresult({results: [Object.assign([{transcript: 'stale'}], {isFinal: true})]});
  assert.deepEqual(sent, []);
});
test('a disconnected recognizer cannot submit provisional words', t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {voice, recognizers, sent} = setup();
  voice.start(true);
  recognizers[0].onresult({results: [Object.assign([{transcript: 'guess'}], {isFinal: false})]});
  recognizers[0].onend();
  t.mock.timers.tick(300);
  assert.deepEqual(sent, []);
  assert.equal(recognizers.length, 2);
  voice.stop();
});
test('dictation keeps the transcript without starting another turn', () => {
  const {voice, recognizers, sent, spoken} = setup();
  voice.start(false);
  recognizers[0].onresult({results: [Object.assign([{transcript: 'edit me'}], {isFinal: true})]});
  assert.deepEqual(sent, ['edit me']);
  assert.equal(voice.active, false);
  voice.reply('silent');
  assert.deepEqual(spoken, []);
});
test('cancelled playback cannot restart the microphone in a new voice session', () => {
  const {voice, recognizers, spoken} = setup();
  voice.start(true);
  recognizers[0].onresult({results: [Object.assign([{transcript: 'hello'}], {isFinal: true})]});
  recognizers[0].onend();
  voice.reply('answer');
  voice.stop();
  voice.start(true);
  spoken[0].onend();
  assert.equal(recognizers.length, 2);
});
test('silence keeps the conversation active and playback errors stop cleanly', t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {voice, recognizers, spoken} = setup();
  voice.start(true);
  recognizers[0].onerror({error: 'no-speech'});
  recognizers[0].onend();
  assert.equal(voice.active, true);
  t.mock.timers.tick(300);
  recognizers[1].onresult({results: [Object.assign([{transcript: 'hello'}], {isFinal: true})]});
  recognizers[1].onend();
  voice.reply('answer');
  spoken[0].onerror();
  assert.equal(voice.active, false);
});
test('pauses collect a full turn; mute and interrupt control the microphone', t => {
  t.mock.timers.enable({apis: ['setTimeout']});
  const {voice, recognizers, spoken, sent} = setup();
  voice.start(true);
  const result = text => recognizers[0].onresult({results: [Object.assign([{transcript: text}], {isFinal: true})]});
  result('first');
  t.mock.timers.tick(1000);
  assert.deepEqual(sent, []);
  result('first and second');
  t.mock.timers.tick(1400);
  assert.deepEqual(sent, ['first and second']);
  voice.reply('answer');
  voice.toggleMute();
  spoken[0].onend();
  assert.equal(recognizers.length, 1);
  voice.toggleMute();
  assert.equal(recognizers.length, 2);
  recognizers[1].onresult({results: [Object.assign([{transcript: 'next'}], {isFinal: true})]});
  recognizers[1].onend();
  voice.reply('next answer');
  voice.interrupt();
  assert.equal(recognizers.length, 3);
  spoken[1].onend();
  assert.equal(recognizers.length, 3);
  voice.stop();
});
