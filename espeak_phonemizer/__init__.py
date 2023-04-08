# coding: utf-8

import ctypes
import os
import sys
import re
import struct
import typing
from pathlib import Path

_DIR = Path(__file__).parent
__version__ = (_DIR / "VERSION").read_text().strip()
ARCH = "x86" if struct.calcsize("P") == 4 else "x64"
ESPEAK_NG_DIR = _DIR / "espeak-ng"
ESPEAK_DATA_PATH = ESPEAK_NG_DIR
ESPEAK_NG_DLL = ESPEAK_NG_DIR / f"espeak-ng-{ARCH}.dll"



class Phonemizer:
    """
    Use espeak-ng shared library to get IPA phonemes from text.
    """

    LANG_SWITCH_FLAG = re.compile(r"\([^)]*\)")
    STRESS_PATTERN = re.compile(r"[ˈˌ]")
    DEFAULT_CLAUSE_BREAKERS = {",", ";", ":", ".", "!", "?"}

    def __init__(
        self,
        default_voice: typing.Optional[str] = None,
        clause_breakers: typing.Optional[typing.Collection[str]] = None,
    ):
        self.current_voice: typing.Optional[str] = None
        self.default_voice = default_voice
        self.clause_breakers = clause_breakers or Phonemizer.DEFAULT_CLAUSE_BREAKERS
        self.dll = ctypes.cdll.LoadLibrary(os.fspath(ESPEAK_NG_DLL.resolve()))
        assert self.dll.espeak_Initialize(None, None, ctypes.c_char_p(os.fspath(ESPEAK_DATA_PATH.resolve()).encode("utf-8")), 7) == 22050
        self.f_text_to_phonemes = self.dll.espeak_TextToPhonemes
        self.f_text_to_phonemes.restype = ctypes.c_char_p
        self.f_text_to_phonemes.argtypes = [
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_int,
            ctypes.c_int
        ]

    def phonemize(
        self,
        text: str,
        voice: typing.Optional[str] = None,
        keep_clause_breakers: bool = False,
        phoneme_separator: typing.Optional[str] = None,
        word_separator: str = " ",
        punctuation_separator: str = "",
        keep_language_flags: bool = False,
        no_stress: bool = False,
    ) -> str:
        """
        Return IPA string for text.

        Args:
            text: Text to phonemize
            voice: optional voice (uses self.default_voice if None)
            keep_clause_breakers: True if punctuation symbols should be kept
            phoneme_separator: Separator character between phonemes
            word_separator: Separator string between words (default: space)
            punctuation_separator: Separator string between before punctuation (keep_clause_breakers=True)
            keep_language_flags: True if language switching flags should be kept
            no_stress: True if stress characters should be removed

        Returns:
            ipa - string of IPA phonemes
        """
        voice = voice or self.default_voice
        if (voice is not None) and (voice != self.current_voice):
            self.current_voice = voice
        assert self.dll.espeak_SetVoiceByName(ctypes.c_char_p(self.current_voice.encode("utf-8"))) == 0

        text += " "
        missing_breakers = []
        if keep_clause_breakers and self.clause_breakers:
            missing_breakers = [c for c in text if c in self.clause_breakers]

        if phoneme_separator is None:
            phoneme_mode = 0x02
        else:
            phoneme_mode = ord(phoneme_separator) << 8 | 0x02

        text_ptr = ctypes.pointer(ctypes.c_char_p(text.encode("utf-8")))
        result = []
        while text_ptr.contents.value is not None:
            phonemes = self.f_text_to_phonemes(text_ptr, 1, phoneme_mode)
            if phonemes:
                result.append(phonemes.decode("utf-8"))
        
        phoneme_lines = "\n".join(result).splitlines()

        if not keep_language_flags:
            # Remove language switching flags, e.g. (en)
            phoneme_lines = [
                Phonemizer.LANG_SWITCH_FLAG.sub("", line) for line in phoneme_lines
            ]

        if word_separator != " ":
            # Split/re-join words
            for line_idx in range(len(phoneme_lines)):
                phoneme_lines[line_idx] = word_separator.join(
                    phoneme_lines[line_idx].split()
                )
        # Re-insert clause breakers
        if missing_breakers:
            # pylint: disable=consider-using-enumerate
            for line_idx in range(len(phoneme_lines)):
                if line_idx < len(missing_breakers):
                    phoneme_lines[line_idx] += (
                        punctuation_separator + missing_breakers[line_idx]
                    )
        phonemes_str = word_separator.join(line.strip() for line in phoneme_lines)
        if no_stress:
            # Remove primary/secondary stress markers
            phonemes_str = Phonemizer.STRESS_PATTERN.sub("", phonemes_str)
        # Clean up multiple phoneme separators
        if phoneme_separator:
            phonemes_str = re.sub(
                "[" + re.escape(phoneme_separator) + "]+",
                phoneme_separator,
                phonemes_str,
            )
        return phonemes_str

    @staticmethod
    def _call_espeakng(args, popen_kwargs=None):
        popen_kwargs = popen_kwargs or {}
        args = [os.fspath(ESPEAK_NG_EXE), *args]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        ret = subprocess.run(
            " ".join(args),
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo,
            **popen_kwargs,
        )
        ret.check_returncode()
        return ret.stdout
