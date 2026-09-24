"""
Default Sound Effects Generator
Generates essential audio effects (beep, whistle, stage_bell, countdown, drum)
using NumPy and SoundFile if they don't already exist.
"""

import os
import io
import numpy as np
import soundfile as sf
from pydub import AudioSegment


def generate_beep(sr=44100, duration=0.25, freq=880.0) -> AudioSegment:
    """880Hz electronic beep sound (0.25s) with attack & decay."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Fundamental + mild overtone for crisp electronic feel
    signal = 0.75 * np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)
    
    # Envelope (smooth fade in / fade out)
    fade_samples = int(sr * 0.01)
    env = np.ones_like(t)
    env[:fade_samples] = np.linspace(0, 1, fade_samples)
    env[-fade_samples:] = np.linspace(1, 0, fade_samples)
    signal = (signal * env * 0.9).astype(np.float32)

    buf = io.BytesIO()
    sf.write(buf, signal, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return AudioSegment.from_file(buf, format='wav')


def generate_whistle(sr=44100, duration=0.35) -> AudioSegment:
    """Referee sports whistle sound (0.35s) with dual frequencies & trill modulation."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Whistle trill (amplitude modulation) around 28Hz
    mod = 0.75 + 0.25 * np.sin(2 * np.pi * 28 * t)
    # Dual whistle frequencies (2500Hz and 2750Hz typical for sports pea-less whistles)
    f1, f2 = 2500.0, 2750.0
    signal = (0.5 * np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t)) * mod
    
    # Slight white noise for breathiness
    noise = np.random.normal(0, 0.05, len(t))
    signal = signal + noise
    
    # Attack / Decay envelope
    env = np.ones_like(t)
    att_samples = int(sr * 0.02)
    dec_samples = int(sr * 0.05)
    env[:att_samples] = np.linspace(0, 1, att_samples)
    env[-dec_samples:] = np.linspace(1, 0, dec_samples)
    signal = (signal * env * 0.85).astype(np.float32)

    buf = io.BytesIO()
    sf.write(buf, signal, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return AudioSegment.from_file(buf, format='wav')


def generate_stage_bell(sr=44100, duration=1.2) -> AudioSegment:
    """Stage level-up 2-tone chime bell (Ding-Dong / E5 -> G#5)."""
    t_half = duration / 2.0
    t1 = np.linspace(0, t_half, int(sr * t_half), endpoint=False)
    t2 = np.linspace(0, t_half, int(sr * t_half), endpoint=False)
    
    # Tone 1: E5 (659.25 Hz)
    decay1 = np.exp(-4.5 * t1)
    s1 = (np.sin(2 * np.pi * 659.25 * t1) + 0.3 * np.sin(2 * np.pi * 1318.5 * t1)) * decay1
    
    # Tone 2: G#5 (830.61 Hz)
    decay2 = np.exp(-3.5 * t2)
    s2 = (np.sin(2 * np.pi * 830.61 * t2) + 0.3 * np.sin(2 * np.pi * 1661.22 * t2)) * decay2
    
    signal = np.concatenate([s1, s2])
    signal = (signal / np.max(np.abs(signal)) * 0.85).astype(np.float32)

    buf = io.BytesIO()
    sf.write(buf, signal, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return AudioSegment.from_file(buf, format='wav')


def generate_countdown(sr=44100) -> AudioSegment:
    """
    3-2-1 electronic countdown followed by a high start buzzer/gun bang.
    Total duration: 3.5 seconds (3 low beeps at 0.0s, 1.0s, 2.0s and high go beep at 3.0s).
    """
    total_sec = 3.6
    total_samples = int(sr * total_sec)
    full_signal = np.zeros(total_samples, dtype=np.float32)

    # 3 short warning beeps at 440Hz (A4)
    def make_short_beep(freq, dur=0.2):
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        env = np.ones_like(t)
        fl = int(sr * 0.01)
        env[:fl] = np.linspace(0, 1, fl)
        env[-fl:] = np.linspace(1, 0, fl)
        return (0.8 * np.sin(2 * np.pi * freq * t) * env).astype(np.float32)

    # 3, 2, 1 beeps
    b_ready = make_short_beep(440.0, 0.22)
    for i, sec_pos in enumerate([0.0, 1.0, 2.0]):
        idx = int(sec_pos * sr)
        full_signal[idx:idx + len(b_ready)] += b_ready

    # Start "GO!" high beep at 3.0s (1174Hz - D6, long & clear)
    b_go = make_short_beep(1174.66, 0.45)
    idx_go = int(3.0 * sr)
    full_signal[idx_go:idx_go + len(b_go)] += b_go

    buf = io.BytesIO()
    sf.write(buf, full_signal, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return AudioSegment.from_file(buf, format='wav')


def generate_drum(sr=44100, duration=0.45) -> AudioSegment:
    """Powerful martial arts impact drum/taiko hit sound."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Pitch drop from 180Hz down to 55Hz
    freq_sweep = np.linspace(180, 55, len(t))
    phase = 2 * np.pi * np.cumsum(freq_sweep) / sr
    
    decay = np.exp(-12.0 * t)
    body = np.sin(phase) * decay
    # Initial punch click / noise
    punch_noise = np.random.normal(0, 0.3, len(t)) * np.exp(-35.0 * t)
    
    signal = body + punch_noise
    signal = (signal / np.max(np.abs(signal)) * 0.9).astype(np.float32)

    buf = io.BytesIO()
    sf.write(buf, signal, sr, format='WAV', subtype='PCM_16')
    buf.seek(0)
    return AudioSegment.from_file(buf, format='wav')


def ensure_default_effects(effects_dir: str = "effects"):
    """Creates default wav assets in effects_dir if missing."""
    os.makedirs(effects_dir, exist_ok=True)
    
    effect_specs = {
        "beep.wav": generate_beep,
        "whistle.wav": generate_whistle,
        "stage_bell.wav": generate_stage_bell,
        "countdown.wav": generate_countdown,
        "drum.wav": generate_drum,
    }

    for filename, gen_fn in effect_specs.items():
        file_path = os.path.join(effects_dir, filename)
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            try:
                audio = gen_fn()
                audio.export(file_path, format="wav")
                print(f"[Effects] Generated default effect asset: {file_path}")
            except Exception as e:
                print(f"[Effects] Error generating {filename}: {e}")
