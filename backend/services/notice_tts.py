"""Spoken SAFETY NOTICES -- our own words, free to hear (bd polyglot-pdf-dft1).

WHY THIS IS NOT THE PAID TTS ROUTE. Both /api/tts/* routes declare
`require_paid_client_work`, which REDEEMS the client's link. That is right for
speech the client asked for, and exactly wrong here:

  - the client who most needs to hear "save your form now" is the one whose
    budget is EXHAUSTED, and a paid route answers them with silence
  - speaking an unsolicited notice would BURN a live client's link, charging
    them for a warning we chose to give

Maintainer, 2026-08-27: our own safety messages must not count against a
client's budget or burn their link -- a few seconds of speech is trivial next
to a voice session, and staying silent costs the client their whole form.

=====================================================================
THE KEYED-ROUTE CONTRACT: CALLER TEXT NEVER BECOMES SPOKEN AUDIO.
=====================================================================

This is the same rule /api/tts/intro already enforces, and it is what stops an
unauthenticated-ish free route from becoming an open text-to-speech service for
anyone with a link. The caller sends a NOTICE KEY and a language name; the text
is looked up HERE, from a table shipped with the server. An unknown key is
refused before anything reaches synthesis.

The notice strings mirror frontend/src/schema-forms/resumeStrings.ts, which is
what the client sees on screen. A parity test pins them together: a client must
never HEAR one thing and READ another.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Optional

import structlog

from backend.services.intro_tts import INTRO_GAIN_DB, resolve_intro_language
from backend.services.spellback_tts import (
    _synthesize_sync,
    resolve_spellback_voice,
)

_log = structlog.get_logger(__name__)

# The notices this route will speak. A key not in here is refused.
NOTICE_SAVE_EARLY = "save_early"
NOTICE_VOICE_ENDING = "voice_ending"

KNOWN_NOTICES = frozenset({NOTICE_SAVE_EARLY, NOTICE_VOICE_ENDING})

# Bounded on OUR side too: these are fixed strings, so a long one is a bug in
# this table rather than caller input, and synthesis cost stays predictable.
MAX_NOTICE_CHARS = 400

# GENERATED FROM frontend/src/schema-forms/resumeStrings.ts -- the text a
# client SEES. Derived rather than hand-written so the spoken and printed
# words cannot drift apart; pinned by test_notice_tts_parity.py.
#
# English is the fallback for any language absent here. NEVER enumerate
# "the supported languages" from this table: 18 today, growing toward ~90.
NOTICE_TEXT: dict[str, dict[str, str]] = {
    "English": {
        NOTICE_SAVE_EARLY: (
            "Save this form to your device now. If you close this page "
            "or stop for a while, you can open the saved file later and"
            " continue where you left off. Nothing is stored on our ser"
            "vers."
        ),
        NOTICE_VOICE_ENDING: (
            "Save your form now so you do not lose your answers. You ca"
            "n still type your remaining answers, and you can still dow"
            "nload and print your form."
        ),
    },
    "Afrikaans": {
        NOTICE_SAVE_EARLY: (
            "Stoor hierdie vorm nou op jou toestel. As jy hierdie blads"
            "y toemaak of n ruk ophou, kan jy die gestoorde leer later "
            "oopmaak en voortgaan waar jy opgehou het. Niks word op ons"
            " bedieners gestoor nie."
        ),
        NOTICE_VOICE_ENDING: (
            "Stoor jou vorm nou sodat jy nie jou antwoorde verloor nie."
            " Jy kan steeds die oorblywende antwoorde intik, en jy kan "
            "steeds jou vorm aflaai en druk."
        ),
    },
    "Arabic": {
        NOTICE_SAVE_EARLY: (
            "احفظ هذه الاستمارة على جهازك الآن. إذا أغلقت هذه الصفحة أو"
            " توقفت لفترة، يمكنك فتح الملف المحفوظ لاحقاً ومتابعة ما تو"
            "قفت عنده. لا يتم تخزين أي شيء على خوادمنا."
        ),
        NOTICE_VOICE_ENDING: (
            "احفظ استمارتك الآن حتى لا تفقد إجاباتك. لا يزال بإمكانك كت"
            "ابة الإجابات المتبقية، ولا يزال بإمكانك تنزيل استمارتك وطب"
            "اعتها."
        ),
    },
    "Chinese": {
        NOTICE_SAVE_EARLY: (
            "请立即将此表格保存到您的设备。如果您关闭此页面或暂停一段时间，稍后可以打开保存的文件，从中断的地方继续。我们的服务器"
            "不会存储任何内容。"
        ),
        NOTICE_VOICE_ENDING: (
            "请立即保存表格，以免丢失您的答案。您仍然可以输入其余答案，也仍然可以下载和打印表格。"
        ),
    },
    "Dutch": {
        NOTICE_SAVE_EARLY: (
            "Sla dit formulier nu op uw apparaat op. Als u deze pagina "
            "sluit of even stopt, kunt u het opgeslagen bestand later o"
            "penen en verdergaan waar u was gebleven. Er wordt niets op"
            " onze servers bewaard."
        ),
        NOTICE_VOICE_ENDING: (
            "Sla uw formulier nu op zodat u uw antwoorden niet kwijtraa"
            "kt. U kunt de resterende antwoorden nog typen en u kunt uw"
            " formulier nog downloaden en afdrukken."
        ),
    },
    "French": {
        NOTICE_SAVE_EARLY: (
            "Enregistrez ce formulaire sur votre appareil maintenant. S"
            "i vous fermez cette page ou vous arretez un moment, vous p"
            "ourrez ouvrir le fichier enregistre plus tard et reprendre"
            " la ou vous en etiez. Rien n est conserve sur nos serveurs"
            "."
        ),
        NOTICE_VOICE_ENDING: (
            "Enregistrez votre formulaire maintenant pour ne pas perdre"
            " vos reponses. Vous pouvez toujours saisir les reponses re"
            "stantes, et vous pouvez toujours telecharger et imprimer v"
            "otre formulaire."
        ),
    },
    "German": {
        NOTICE_SAVE_EARLY: (
            "Speichern Sie dieses Formular jetzt auf Ihrem Geraet. Wenn"
            " Sie diese Seite schliessen oder eine Pause machen, koenne"
            "n Sie die gespeicherte Datei spaeter oeffnen und dort weit"
            "ermachen, wo Sie aufgehoert haben. Auf unseren Servern wir"
            "d nichts gespeichert."
        ),
        NOTICE_VOICE_ENDING: (
            "Speichern Sie Ihr Formular jetzt, damit Ihre Antworten nic"
            "ht verloren gehen. Sie koennen die restlichen Antworten we"
            "iterhin eingeben und Ihr Formular weiterhin herunterladen "
            "und drucken."
        ),
    },
    "Hindi": {
        NOTICE_SAVE_EARLY: (
            "इस फॉर्म को अभी अपने डिवाइस में सहेजें। यदि आप यह पेज बंद "
            "करते हैं या कुछ समय के लिए रुकते हैं, तो आप बाद में सहेजी "
            "गई फ़ाइल खोलकर वहीं से जारी रख सकते हैं। हमारे सर्वर पर कु"
            "छ भी संग्रहीत नहीं होता।"
        ),
        NOTICE_VOICE_ENDING: (
            "अपने उत्तर खोने से बचने के लिए अभी अपना फॉर्म सहेजें। आप श"
            "ेष उत्तर टाइप कर सकते हैं, और अपना फॉर्म डाउनलोड और प्रिंट"
            " भी कर सकते हैं।"
        ),
    },
    "Italian": {
        NOTICE_SAVE_EARLY: (
            "Salva ora questo modulo sul tuo dispositivo. Se chiudi que"
            "sta pagina o ti fermi per un po, potrai aprire il file sal"
            "vato piu tardi e riprendere da dove avevi lasciato. Nulla "
            "viene conservato sui nostri server."
        ),
        NOTICE_VOICE_ENDING: (
            "Salva ora il modulo per non perdere le tue risposte. Puoi "
            "ancora digitare le risposte rimanenti e puoi ancora scaric"
            "are e stampare il modulo."
        ),
    },
    "Korean": {
        NOTICE_SAVE_EARLY: (
            "지금 이 양식을 기기에 저장하세요. 이 페이지를 닫거나 잠시 중단하더라도 나중에 저장한 파일을 열어 중단"
            "한 곳부터 계속할 수 있습니다. 저희 서버에는 아무것도 저장되지 않습니다."
        ),
        NOTICE_VOICE_ENDING: (
            "답변을 잃지 않도록 지금 양식을 저장하세요. 남은 답변은 직접 입력할 수 있으며, 양식을 다운로드하고 인"
            "쇄하는 것도 계속 가능합니다."
        ),
    },
    "Persian": {
        NOTICE_SAVE_EARLY: (
            "اکنون این فرم را در دستگاه خود ذخیره کنید. اگر این صفحه را"
            " ببندید یا مدتی متوقف شوید، می‌توانید بعداً فایل ذخیره‌شده"
            " را باز کنید و از همان‌جا ادامه دهید. هیچ چیزی روی سرورهای"
            " ما ذخیره نمی‌شود."
        ),
        NOTICE_VOICE_ENDING: (
            "اکنون فرم خود را ذخیره کنید تا پاسخ‌هایتان از بین نرود. هم"
            "چنان می‌توانید پاسخ‌های باقی‌مانده را تایپ کنید و فرم خود "
            "را دانلود و چاپ کنید."
        ),
    },
    "Portuguese": {
        NOTICE_SAVE_EARLY: (
            "Salve este formulario no seu dispositivo agora. Se voce fe"
            "char esta pagina ou parar por um tempo, podera abrir o arq"
            "uivo salvo mais tarde e continuar de onde parou. Nada fica"
            " armazenado em nossos servidores."
        ),
        NOTICE_VOICE_ENDING: (
            "Salve seu formulario agora para nao perder suas respostas."
            " Voce ainda pode digitar as respostas restantes e ainda po"
            "de baixar e imprimir seu formulario."
        ),
    },
    "Russian": {
        NOTICE_SAVE_EARLY: (
            "Сохраните эту форму на своё устройство сейчас. Если вы зак"
            "роете страницу или прервётесь, вы сможете позже открыть со"
            "хранённый файл и продолжить с того места, где остановились"
            ". На наших серверах ничего не хранится."
        ),
        NOTICE_VOICE_ENDING: (
            "Сохраните форму сейчас, чтобы не потерять ответы. Вы по-пр"
            "ежнему можете вписать оставшиеся ответы, а также скачать и"
            " распечатать форму."
        ),
    },
    "Spanish": {
        NOTICE_SAVE_EARLY: (
            "Guarde este formulario en su dispositivo ahora. Si cierra "
            "esta pagina o se detiene por un tiempo, puede abrir el arc"
            "hivo guardado mas tarde y continuar donde lo dejo. No se g"
            "uarda nada en nuestros servidores."
        ),
        NOTICE_VOICE_ENDING: (
            "Guarde su formulario ahora para no perder sus respuestas. "
            "Todavia puede escribir las respuestas que faltan, y todavi"
            "a puede descargar e imprimir su formulario."
        ),
    },
    "Swedish": {
        NOTICE_SAVE_EARLY: (
            "Spara det har formularet pa din enhet nu. Om du stanger si"
            "dan eller tar en paus kan du oppna den sparade filen senar"
            "e och fortsatta dar du slutade. Ingenting lagras pa vara s"
            "ervrar."
        ),
        NOTICE_VOICE_ENDING: (
            "Spara ditt formular nu sa att du inte forlorar dina svar. "
            "Du kan fortfarande skriva in de svar som aterstar, och du "
            "kan fortfarande ladda ner och skriva ut ditt formular."
        ),
    },
    "Tagalog": {
        NOTICE_SAVE_EARLY: (
            "I-save ang form na ito sa inyong device ngayon. Kung isasa"
            "ra ninyo ang pahinang ito o titigil kayo saglit, mabubuksa"
            "n ninyo ang na-save na file mamaya at maipagpapatuloy kung"
            " saan kayo tumigil. Walang naka-imbak sa aming mga server."
        ),
        NOTICE_VOICE_ENDING: (
            "I-save ang inyong form ngayon para hindi mawala ang inyong"
            " mga sagot. Maaari pa rin kayong mag-type ng natitirang sa"
            "got, at maaari pa rin kayong mag-download at mag-print ng "
            "inyong form."
        ),
    },
    "Ukrainian": {
        NOTICE_SAVE_EARLY: (
            "Збережіть цю форму на своєму пристрої зараз. Якщо ви закри"
            "єте цю сторінку або зробите перерву, ви зможете відкрити з"
            "бережений файл пізніше й продовжити з того місця, де зупин"
            "илися. На наших серверах нічого не зберігається."
        ),
        NOTICE_VOICE_ENDING: (
            "Збережіть форму зараз, щоб не втратити відповіді. Ви все щ"
            "е можете вписати решту відповідей, а також завантажити та "
            "роздрукувати форму."
        ),
    },
    "Urdu": {
        NOTICE_SAVE_EARLY: (
            "یہ فارم ابھی اپنے آلے میں محفوظ کریں۔ اگر آپ یہ صفحہ بند ک"
            "ر دیں یا کچھ دیر رک جائیں، تو آپ بعد میں محفوظ شدہ فائل کھ"
            "ول کر وہیں سے جاری رکھ سکتے ہیں۔ ہمارے سرورز پر کچھ محفوظ "
            "نہیں ہوتا۔"
        ),
        NOTICE_VOICE_ENDING: (
            "اپنے جوابات ضائع ہونے سے بچانے کے لیے ابھی اپنا فارم محفوظ"
            " کریں۔ آپ باقی جوابات ٹائپ کر سکتے ہیں، اور اپنا فارم ڈاؤن"
            " لوڈ اور پرنٹ بھی کر سکتے ہیں۔"
        ),
    },
}


def notice_text(language_name: Optional[str], notice_key: str) -> str:
    """The text for this notice, in this language. Raises on an unknown key.

    Falls back to English for a language we have no translation for, which is
    how a newly-supported language degrades to something audible rather than to
    silence.
    """
    if notice_key not in KNOWN_NOTICES:
        raise ValueError("unknown notice")
    table = NOTICE_TEXT.get(language_name or "", NOTICE_TEXT["English"])
    text = table.get(notice_key) or NOTICE_TEXT["English"][notice_key]
    if len(text) > MAX_NOTICE_CHARS:
        # Our own table is too long: a bug here, never caller input.
        raise ValueError("notice text too long")
    return text


async def synthesize_notice(
    language_name: Optional[str], notice_key: str, settings
) -> tuple[bytes, str]:
    """Synthesize a fixed safety notice. Returns (mp3_bytes, etag).

    Raises ValueError on an unknown key -- the route maps that to a 400 before
    anything reaches the TTS backend.
    """
    text = notice_text(language_name, notice_key)          # raises on unknown
    language = resolve_intro_language(language_name)

    def _resolve_and_synthesize() -> bytes:
        # Same voice resolution and gain as the intro clip, so a notice does
        # not arrive noticeably louder or quieter than the app's other speech.
        voice_name, locale = resolve_spellback_voice(settings, language)
        return _synthesize_sync(text, voice_name, locale, gain_db=INTRO_GAIN_DB)

    # Off the event loop: voice resolution is a network RPC on first use, and
    # synthesis is blocking. Same discipline as the intro and spellback paths.
    audio = await asyncio.to_thread(_resolve_and_synthesize)

    etag = '"notice-%s"' % hashlib.sha256(audio).hexdigest()[:24]

    _log.info(
        "notice_tts_synthesized",
        notice=notice_key,
        language=language,
        bytes=len(audio),
    )
    return audio, etag
