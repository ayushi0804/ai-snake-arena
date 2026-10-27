/* Arena.sound - tiny WebAudio synth (no audio files, works offline). */
(function (root) {
  'use strict';
  const A = root.Arena; let ctx = null, muted = false, volume = 0.5;
  const TONES = { apple: [[660, .07], [880, .08]], bonus: [[880, .06], [1175, .06], [1568, .1]], powerup: [[520, .06], [780, .06], [1040, .1]],
    die: [[330, .15], [220, .15], [147, .3]], won: [[523, .1], [659, .1], [784, .1], [1047, .3]], turn: [[300, .015]] };
  function ensure() { if (!ctx) { const C = root.AudioContext || root.webkitAudioContext; if (!C) return null; ctx = new C(); } if (ctx.state === 'suspended') ctx.resume(); return ctx; }
  A.sound = {
    configure(s) { muted = !s.sound; volume = s.volume; },
    setMuted(m) { muted = m; }, isMuted: () => muted,
    unlock() { ensure(); },
    play(name) {
      if (muted || volume <= 0) return; const c = ensure(); if (!c || !TONES[name]) return;
      let t = c.currentTime;
      for (const [f, d] of TONES[name]) {
        const o = c.createOscillator(), g = c.createGain();
        o.type = name === 'die' ? 'sawtooth' : 'square'; o.frequency.value = f;
        g.gain.setValueAtTime(0.12 * volume, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
        o.connect(g).connect(c.destination); o.start(t); o.stop(t + d + 0.02); t += d;
      }
    },
  };
})(window);
