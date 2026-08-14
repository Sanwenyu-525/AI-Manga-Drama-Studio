# Design QA — AI Manga Drama Studio

## Comparison target

- Source visual truth:
  - `stitch_ai_manga_drama_studio/project_home_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/new_project_import_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/novel_analysis_preview_director_s_console/screen.png`
  - `stitch_ai_manga_drama_studio/screen.png`（Storyboard）
- Rendered implementation: `http://localhost:4173/`
- Browser-rendered evidence:
  - `.design-qa/preview-home.png`
  - `.design-qa/new-project-implementation.png`
  - `.design-qa/analysis-implementation.png`
  - `.design-qa/storyboard-implementation.png`
  - `.design-qa/inspector-implementation.png`
  - `.design-qa/director-implementation.png`
  - `.design-qa/version-review-implementation.png`

## Viewport and normalization

- Source pixels: 1600 × 1280, desktop dark theme.
- Browser CSS viewport: 1600 × 1280; browser-reported device pixel ratio: 1.25.
- Full-page captures: 1600 × 1280. Home and New Project were compared at full size.
- Studio viewport captures: 1600 × 1065 because the desktop app browser reserves host chrome vertically. The matching source was cropped to the same 1600 × 1065 top viewport before comparison; no scaling was applied.
- Narrow desktop check: 1100 × 900 CSS pixels, no horizontal document overflow (`scrollWidth === innerWidth`).
- State: real local Project State, Stage B fake LLM preview, Stage C Mock Image Provider, Stage D not connected.

## Full-view comparison evidence

- `.design-qa/home-comparison-final.png`
- `.design-qa/new-project-comparison-final.png`
- `.design-qa/storyboard-comparison-final.png`
- `.design-qa/analysis-comparison-final.png`

The implementation preserves the source composition: near-black multi-panel canvas, amber navigation and primary actions, compact technical typography, thin dividers, vertical manga imagery, five-region Studio shell, storyboard card grid, tri-column analysis review, right inspector, and bottom generation dock.

## Focused region comparison

- New Project: header, settings controls, start-mode cards, vertical cover preview, project specs, and workflow ribbon were checked in the full-size 1600 × 1280 comparison.
- Storyboard: project tree, scene header, shot-card density, selected state, Inspector state, and bottom queue were checked in the 1600 × 1065 comparison and separate Inspector capture.
- Analysis: source editor, scene list, selected scene details, analysis stepper, and confirm action were checked in the analysis comparison.
- Version review and AI Director were checked as implementation-only states because their Stitch references contain known visual/content conflicts (white rendering artifacts, unrelated photography, and Stage D behavior not yet backed by API).

## Required fidelity surfaces

- Fonts and typography: Geist Variable is bundled locally; Chinese uses the system CJK fallback. Weight, uppercase technical labels, numeric alignment, compact small text, and hierarchy are consistent with the references.
- Spacing and layout rhythm: 55–58 px persistent bars, 300/920/380 Studio tracks at 1600 px, thin panel separators, compact 4–7 px radii, and dense shot cards match the desktop production-console intent.
- Colors and tokens: `#0D0F13`, `#14171D`, `#1B1F27`, `#E8A33D`, muted steel text, green success, and red failure states are consistently tokenized.
- Image quality: the supplied 768 × 1376 manga asset is used directly and cropped with `object-fit: cover`; no CSS art, emoji, handcrafted SVG, or placeholder glyph replaces visible artwork. Existing Mock Provider assets remain visible when they are the server truth.
- Copy and content: UI copy is unified to Chinese while preserving stable production terms such as Shot, Storyboard, Project State, ComfyUI, V1/V2, and AI Director.
- Icons: all UI icons come from Phosphor Icons with a consistent optical weight; no inline SVG is used.
- Accessibility: semantic buttons/links/labels, focus-visible outlines, disabled states, alt text, and color-plus-text status indicators are present.

## Primary interactions tested

- Project selection and opening the Studio.
- New Project form: aspect ratio, FPS, and start mode controls.
- Episode source editor and non-writing AI analysis preview.
- Scene selection → Storyboard loading.
- Shot selection → Inspector loading and revision-aware fields.
- Top-bar generation action remains disabled without a selected Shot and becomes enabled after Shot selection.
- AI Director tab and honest Stage D locked state.
- Generation queue expand/collapse and history tab.
- Version review selection and active-version state.
- Production preview console: no warnings or errors in a fresh browser tab.
- `npm run build`: passed.

## Comparison history

### Pass 1

- [P2] Home cover and feature card were too short relative to the source, weakening the vertical editorial composition.
- [P2] Home content margins and recent-project column were narrower than the 1600 px reference.
- [P2] New Project wordmark auto-placed into the wrong header column.

Fixes:

- Made the cover fill the project feature card with a 720 px minimum and removed the 680 px cap.
- Aligned the Home canvas to a 1440 px content frame with a 400 px recent-project column at the reference viewport.
- Assigned the New Project wordmark and back button to explicit header grid positions.

### Pass 2

- Post-fix evidence: `.design-qa/home-comparison-final.png` and `.design-qa/new-project-comparison-final.png`.
- No actionable P0/P1/P2 visual or interaction findings remain.

## Accepted constraints / P3 follow-up

- Home metrics in the Stitch mock are not displayed because the current API has no project aggregate endpoint; the implementation shows only server-backed project fields.
- The Stitch visual-style picker is omitted because MVP Project State has no corresponding persisted field. Adding a cosmetic-only selector would misrepresent saved behavior.
- Mock Image Provider output is intentionally shown as returned by Stage C; production ComfyUI imagery will replace it without a UI change.
- AI Director shows a truthful Stage D readiness state instead of fabricating approval or completed runs.

final result: passed
