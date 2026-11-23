class VoiceChat {
  constructor(options) { Object.assign(this, options); this.active = false; }

  stop(message = 'Voice off') {
    clearTimeout(this.turnTimer);
    clearTimeout(this.restartTimer);
    this.muted = false;
    this.active = false;
    this.utterance = null;
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
    this.speech?.cancel();
    this.onState(message);
  }

  start(conversation) {
    this.stop();
    this.active = true;
    this.conversation = conversation;
    this.listen();
  }

  listen() {
    if (!this.active) return;
    if (this.muted) { this.onState('Microphone muted'); return; }
    this.waiting = false;
    const recognition = new this.Recognition();
    this.recognition = recognition;
    recognition.lang = this.lang;
    recognition.continuous = this.conversation;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    let final = false;
    let transcript = '';
    const finish = () => {
      if (this.recognition !== recognition || final || !transcript) return;
      final = true;
      clearTimeout(this.turnTimer);
      this.recognition = null;
      recognition.abort();
      if (!this.conversation) this.stop('Dictation ready — review and send.');
      else { this.waiting = true; this.onState('Thinking…'); }
      this.onTranscript(transcript, this.conversation);
    };
    recognition.onstart = () => {
      if (this.recognition === recognition) this.onState('Listening…');
    };
    recognition.onresult = event => {
      if (this.recognition !== recognition || final) return;
      const results = Array.from(event.results);
      const text = results.map(result => result[0].transcript).join(' ').trim();
      clearTimeout(this.turnTimer);
      // Never submit a provisional recognition guess when the service disconnects.
      transcript = results.every(result => result.isFinal) ? text : '';
      this.onState(`Heard: ${text}`);
      if (!results.every(result => result.isFinal) || !text) return;
      if (this.conversation) this.turnTimer = setTimeout(finish, 1400);
      else finish();
    };
    recognition.onerror = event => {
      if (this.recognition !== recognition) return;
      if (event.error === 'no-speech') return;
      const errors = {
        'not-allowed': 'Microphone access denied. Allow it in browser settings.',
        'audio-capture': 'No microphone available. Check your input device.',
        'network': 'Speech service unavailable. Check your connection.',
        'language-not-supported': 'This speech language is unavailable in your browser.',
      };
      this.stop(errors[event.error] || `Speech recognition stopped: ${event.error}`);
    };
    recognition.onend = () => {
      if (this.recognition !== recognition) return;
      if (transcript) { finish(); return; }
      this.recognition = null;
      if (this.conversation && this.active) {
        this.onState('Listening…');
        this.restartTimer = setTimeout(() => this.listen(), 300);
      } else this.stop('No speech detected. Click to try again.');
    };
    try { recognition.start(); }
    catch { this.stop('Could not start microphone. Click to try again.'); }
  }

  toggleMute() {
    if (!this.active) return;
    this.muted = !this.muted;
    clearTimeout(this.turnTimer);
    clearTimeout(this.restartTimer);
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.abort();
    if (!this.waiting && !this.utterance) this.listen();
    else this.onState(this.utterance ? 'Speaking…' : 'Thinking…');
  }

  interrupt() {
    if (!this.active || !this.utterance) return;
    this.utterance = null;
    this.speech.cancel();
    this.listen();
  }

  reply(text) {
    if (!this.active || !this.conversation) return;
    this.waiting = false;
    const utterance = new this.Utterance();
    utterance.text = text;
    utterance.lang = this.lang;
    const voices = this.speech.getVoices();
    utterance.voice = voices.find(v => v.lang.toLowerCase() === this.lang.toLowerCase())
      || voices.find(v => v.lang.split('-')[0] === this.lang.split('-')[0]) || null;
    utterance.onend = () => { if (this.utterance === utterance && this.active) { this.utterance = null; this.listen(); } };
    utterance.onerror = () => { if (this.utterance === utterance && this.active) this.stop('Speech playback failed. Click to try again.'); };
    this.utterance = utterance;
    this.onState('Speaking…');
    try { this.speech.speak(utterance); }
    catch { this.stop('Speech playback unavailable.'); }
  }
}
if (typeof module !== 'undefined') module.exports = {VoiceChat};
