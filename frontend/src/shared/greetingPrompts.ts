/**
 * Greeting prompts for language carousel
 * Shows activation phrases in different languages to initiate conversation with Gemini
 * Used to prompt user to start speaking in their preferred language
 *
 * Source: planning_documents/hello_gemini_translations.csv
 * Updated to match confirmed working activation phrases for Gemini
 */

export interface GreetingPrompt {
  language: string
  code: string
  text: string
}

/**
 * Greeting prompts in various languages
 * Format: Activation phrase to speak to Gemini (e.g., "Hello Gemini, please speak English")
 * Curated selection of 18 languages confirmed to work with Gemini
 */
export const GREETING_PROMPTS: GreetingPrompt[] = [
  { language: 'English', code: 'en', text: 'Hello Gemini, please speak English' },
  { language: 'Español', code: 'es', text: 'Hola Gemini, por favor habla español' },
  { language: '中文', code: 'zh-Hans', text: '你好 Gemini, 请说中文' },
  { language: 'Tagalog', code: 'tl', text: 'Kumusta Gemini, pakisabi sa Tagalog' },
  { language: 'العربية', code: 'ar', text: 'مرحباً يا جيميناي، من فضلك تحدث العربية' },
  { language: 'Français', code: 'fr', text: 'Bonjour Gemini, veuillez parler français' },
  { language: '한국어', code: 'ko', text: '안녕하세요 Gemini, 한국어로 말해주세요' },
  { language: 'Deutsch', code: 'de', text: 'Hallo Gemini, sprich bitte Deutsch' },
  { language: 'Português', code: 'pt', text: 'Olá Gemini, por favor, fale português' },
  { language: 'हिन्दी', code: 'hi', text: 'नमस्ते जेमिनी, कृपया हिंदी बोलें' },
  { language: 'Italiano', code: 'it', text: 'Ciao Gemini, parla italiano per favore' },
  { language: 'اردو', code: 'ur', text: 'ہیلو جیمنی، برائے مہربانی اردو بولیں' },
  { language: 'فارسی', code: 'fa', text: 'سلام جیمینی، لطفا فارسی صحبت کن' },
  { language: 'Nederlands', code: 'nl', text: 'Hallo Gemini, spreek alstublieft Nederlands' },
  { language: 'Українська', code: 'uk', text: 'Привіт Gemini, будь ласка, говори українською' },
  { language: 'Svenska', code: 'sv', text: 'Hej Gemini, tala svenska tack' },
  { language: 'Afrikaans', code: 'af', text: 'Hallo Gemini, praat asseblief Afrikaans' },
  { language: 'Qhichwa', code: 'qu', text: 'Allillanchu Gemini, ama hina kaychu, Qhichwa rimay' },
]
