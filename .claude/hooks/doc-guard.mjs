#!/usr/bin/env node
// PostToolUse(Edit|Write|MultiEdit): Maily 문서 거버넌스 가드.
// 1) 거버넌스/스펙 .md 변경 감지 → 크로스-문서 재점검 리마인더.
// 2) 활성 기준 .md가 허용 경로 밖에 생성/수정되면 배치 규칙 경고.
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
if (!file.endsWith('.md')) emit();

const root = data?.cwd || process.env.CLAUDE_PROJECT_DIR || '';
const rel = root && file.startsWith(root) ? file.slice(root.length).replace(/^\//, '') : file;

// 인프라·의존성 경로는 문서 거버넌스 대상이 아니다.
if (rel.startsWith('.') || rel.includes('node_modules/')) emit();

const GOVERNANCE = ['CLAUDE.md', 'AGENTS.md', 'README.md', 'PRODUCT.md', 'DESIGN.md'];
const isGovernance = GOVERNANCE.includes(rel) || rel.startsWith('docs/');

function placementOk(p) {
  if (!p.includes('/')) return GOVERNANCE.includes(p); // repo root .md
  if (p.startsWith('development/')) return p.endsWith('README.md'); // 코드 영역은 README만
  return ['docs/', 'design/', 'planning/', 'archive/'].some((d) => p.startsWith(d));
}

const notes = [];
if (isGovernance) {
  notes.push(
    `거버넌스/스펙 문서 변경 감지: ${rel}. 단일 근거 확인 — 우선순위→docs/CONTEXT.md, 배치→AGENTS.md, 제품→PRODUCT.md, 시각→DESIGN.md, 카피→design/copy-principles.md. 크로스-문서 모순·중복 우려 시 /doc-audit 실행.`,
  );
}
if (!placementOk(rel)) {
  notes.push(
    `배치 규칙: 활성 기준 .md는 docs/current|areas|goals(또는 design/·development README)에 둔다. '${rel}'는 허용 경로 밖 — 위치 재확인.`,
  );
}

emit(notes.join(' '));
