#!/usr/bin/env node
// PostToolUse(Edit|Write|MultiEdit): Maily 백엔드 로깅/에러 가드.
// docs/areas/backend/error-handling-and-logging.md 기준 위반 감지 시 리마인더.
// 1) print( 사용 → structlog logger로 교체 권고.
// 2) raise ValueError/Exception/HTTPException 직접 사용 → MailyError 서브클래스 권고.
// 3) logger.info/warning/error(...) 첫 인자에 한국어 문자 없음 → 로그 메시지 언어 규칙 리마인더.
// 비차단: 항상 exit 0. 필요 시 additionalContext로만 리마인더 주입.
import { readFileSync } from 'node:fs';

function emit(context) {
  if (context) {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: { hookEventName: 'PostToolUse', additionalContext: context },
      }),
    );
  } else {
    process.stdout.write('{}');
  }
  process.exit(0);
}

let data;
try {
  data = JSON.parse(readFileSync(0, 'utf8') || '{}');
} catch {
  emit();
}

const file = data?.tool_input?.file_path || '';
if (!file.endsWith('.py')) emit();

const root = data?.cwd || process.env.CLAUDE_PROJECT_DIR || '';
const rel = root && file.startsWith(root) ? file.slice(root.length).replace(/^\//, '') : file;

if (!rel.startsWith('development/backend/')) emit();
if (rel.startsWith('development/backend/tests/')) emit(); // 테스트는 도메인 예외/로깅 규칙 대상 아님
if (rel.endsWith('/security.py') || rel.endsWith('/crypto.py')) emit(); // 저수준 예외 소유 파일은 예외

let content;
try {
  content = readFileSync(file, 'utf8');
} catch {
  emit();
}

const HANGUL = /[ㄱ-ㆎ가-힣]/;
const notes = [];

if (/(^|\s)print\(/.test(content)) {
  notes.push(
    `${rel}: print( 사용 감지. structlog logger로 교체(docs/areas/backend/error-handling-and-logging.md 원칙 6).`,
  );
}

if (/raise\s+(ValueError|Exception)\(/.test(content) || /raise\s+HTTPException\(/.test(content)) {
  notes.push(
    `${rel}: raw ValueError/Exception/HTTPException 감지. app.core.errors의 MailyError 서브클래스만 사용(같은 문서 설계 원칙 1).`,
  );
}

const loggerCallRe = /logger\.(info|warning|error)\(\s*["']([^"']*)["']/g;
let match;
const nonKoreanMessages = [];
while ((match = loggerCallRe.exec(content)) !== null) {
  const message = match[2];
  if (message && !HANGUL.test(message)) nonKoreanMessages.push(message);
}
if (nonKoreanMessages.length > 0) {
  notes.push(
    `${rel}: logger 호출 메시지가 한국어가 아님(${nonKoreanMessages.slice(0, 3).join(', ')}). ` +
      `로그 메시지(첫 인자)는 한국어, 필드 키만 영어(같은 문서 설계 원칙 8, ~/.claude/CLAUDE.md).`,
  );
}

emit(notes.join(' '));
