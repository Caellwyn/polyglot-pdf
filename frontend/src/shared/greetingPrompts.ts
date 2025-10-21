/**
 * Greeting prompts for language carousel
 * Shows "Say 'Hello Gemini' in your native language" in different languages
 * Used to prompt user to initiate conversation in their preferred language
 * 
 * Translations provided for 100+ languages - carousel selects 30 for display
 */

export interface GreetingPrompt {
  language: string
  code: string
  text: string
}

/**
 * Greeting prompts in various languages
 * Format: Instruction to say "Hello Gemini" in user's native language
 * Curated selection of 30 most widely spoken languages for the carousel
 */
export const GREETING_PROMPTS: GreetingPrompt[] = [
  { language: 'English', code: 'en', text: 'Say "Hello Gemini" in your native language' },
  { language: 'Spanish', code: 'es', text: 'Di \'Hola Géminis\' en tu idioma nativo.' },
  { language: 'Chinese (Simplified)', code: 'zh-Hans', text: '用你的母语说"你好，双子座"。' },
  { language: 'Hindi', code: 'hi', text: 'अपनी मूल भाषा में "नमस्ते जेमिनी" कहिए।' },
  { language: 'Arabic', code: 'ar', text: 'قل "مرحباً يا چيميني" بلغتك الأم.' },
  { language: 'Portuguese', code: 'pt', text: 'Diga "Olá Gemini" na sua língua nativa.' },
  { language: 'Bengali', code: 'bn', text: 'আপনার মাতৃভাষায় \'হ্যালো জেমিনি\' বলুন।' },
  { language: 'Russian', code: 'ru', text: 'Скажи «Привет, Джемини» на своём родном языке.' },
  { language: 'Japanese', code: 'ja', text: '母国語で「こんにちは、ジェミニ」と言ってください。' },
  { language: 'Punjabi', code: 'pa', text: 'ਆਪਣੀ ਮਾਂ ਬੋਲੀ ਵਿੱਚ "ਹੈਲੋ ਜੈਮਿਨੀ" ਕਹੋ।' },
  { language: 'German', code: 'de', text: 'Sag "Hallo Gemini" in deiner Muttersprache.' },
  { language: 'Javanese', code: 'jv', text: 'Ucapake \'Halo Gemini\' nganggo basa ibumu.' },
  { language: 'Korean', code: 'ko', text: '모국어로 "안녕하세요 제미나이"라고 말해 주세요.' },
  { language: 'French', code: 'fr', text: 'Dis "Bonjour Gemini" dans ta langue maternelle.' },
  { language: 'Turkish', code: 'tr', text: 'Ana dilinde "Merhaba Gemini" de.' },
  { language: 'Vietnamese', code: 'vi', text: 'Nói "Chào Gemini" bằng tiếng mẹ đẻ của bạn.' },
  { language: 'Italian', code: 'it', text: 'Di\' "Ciao Gemini" nella tua lingua madre.' },
  { language: 'Thai', code: 'th', text: 'พูดว่า "สวัสดี Gemini" ในภาษาแม่ของคุณ.' },
  { language: 'Persian', code: 'fa', text: 'به زبان مادری خود بگویید \'سلام جِمینی\'.' },
  { language: 'Polish', code: 'pl', text: 'Powiedz „Cześć Gemini" w swoim języku ojczystym.' },
  { language: 'Ukrainian', code: 'uk', text: 'Скажи «Привіт, Дженімі» своєю рідною мовою.' },
  { language: 'Urdu', code: 'ur', text: 'اپنی مادری زبان میں \'ہیلو جیمنی\' کہیں۔' },
  { language: 'Indonesian', code: 'id', text: 'Ucapkan \'Halo Gemini\' dalam bahasa ibumu.' },
  { language: 'Dutch', code: 'nl', text: 'Zeg "Hallo Gemini" in je moedertaal.' },
  { language: 'Greek', code: 'el', text: 'Πες «Γεια σου Gemini» στη μητρική σου γλώσσα.' },
  { language: 'Czech', code: 'cs', text: 'Řekněte „Ahoj Gemini" ve svém rodném jazyce.' },
  { language: 'Swedish', code: 'sv', text: 'Säg "Hej Gemini" på ditt modersmål.' },
  { language: 'Romanian', code: 'ro', text: 'Spune "Salut Gemini" în limba ta maternă.' },
  { language: 'Hebrew', code: 'iw', text: 'אמור "שלום ג\'מיני" בשפת האם שלך.' },
  { language: 'Swahili', code: 'sw', text: 'Sema \'Habari Gemini\' kwa lugha yako ya asili.' },
]
