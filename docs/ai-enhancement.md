# AI Enhancement

The **AI Enhancement** toolbar button opens an upload, chat and result window, even
before an image is loaded. Upload/change the image in the window, describe the edit,
and click **Enhance with AI**. The initial example asks to suppress heat colors from
mountains, sky and tower while preserving the insulator and keeping the scene blue.
AI chooses the target; manual drawing is not the first step.

Compare **Before / After**, request another adjustment in chat, then click **Use this
result**. **Done — return to image** returns to the workspace; Save draft or Save to
inspection persists it. Applying is one undoable adjustment. Selection outlines are
hidden by default and manual refinement is under **Manual controls (optional)**.
A clarification or failed request cannot apply a previous pending result. Switching
images clears chat, pending results and in-flight requests so edits stay with the
selected image. Provider connection and image readiness must complete before sending.

The AI produces approximate visual selections, not guaranteed pixel-perfect
segmentation. Check insulator edges in the preview. Source pixels and calibrated
temperatures remain preserved; background blue is a display treatment. Original
measurements are not rewritten to zero. The selected provider receives a visual
preview only when the user sends a message.

## Server setup

Sign in as an administrator and open **Settings → AI connection**. Select
**OpenAI**, **Anthropic (Claude)**, or **Google (Gemini)**, choose a model ID,
and paste the key issued by that provider. Click **Save AI settings**, then
**Test connection**. Provider, model and key activate together; no restart is needed.
The test sends a short text request to the saved provider, uses API quota, and
sends no image. It verifies access; it does not assess image-selection quality.
Saved keys are never returned to the browser. Each provider retains its own key
and model. Leave the key blank to reuse that provider's saved key. Switching to
a provider without a key is rejected. Only administrators can save or test settings.

The app saves `AI_PROVIDER`, provider model settings, and `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `GEMINI_API_KEY` in `STORAGE_ROOT/ai-settings/.env` (production:
`/data/ai-settings/.env` in the persistent `thermal_data` volume), separate from
the deployment environment. On Linux its directory is owner-only `0700` and the
file is `0600`. Writes are atomic; errors and activity logs exclude credentials.
Back up this private file along with the volume; never commit it or include it in
image exports. The production deployment script includes it in protected backups.
It survives container recreation. Saved values take precedence over the matching
deployment environment values. Missing values fall back to configuration defaults.
Existing OpenAI-only files remain compatible. The application does not modify the
root deployment `.env`.

Models must support image understanding and structured output. The model selector
offers several curated choices for each provider, including GPT-4.1/mini, GPT-5 mini,
GPT-6 Luna and GPT-6.1 Sol; Claude Sonnet/Haiku/Opus 5.5; and Gemini 3.8 Flash,
3.6 Flash and 3.5 Flash-Lite. These are suggestions, not a list of account permissions.
Choose **Custom model ID** for another compatible model available to your account.
Existing saved model IDs (including custom IDs) and keys are preserved; selection
changes take effect only after saving. Catalog checked on 2026-10-10 against
[OpenAI](https://developers.openai.com/api/docs/models),
[Anthropic](https://platform.claude.com/docs/en/models/overview), and
[Google](https://ai.google.dev/gemini-api/docs/models). Model settings are saved separately
as `OPENAI_ENHANCEMENT_MODEL`, `ANTHROPIC_ENHANCEMENT_MODEL`, and
`GEMINI_ENHANCEMENT_MODEL`. Account access and actual image quality require live testing.
Existing online reference search continues to use the separately saved OpenAI key
and `OPENAI_WEB_MODEL`; the provider selector controls image enhancement only.
With no key, the dialog explains setup and offers the manual focus tool. There is no
simulated AI fallback in production. Provider authentication, model availability, and
billing/quota errors are reported without exposing the key or upstream response body.

## What happens

- Authenticated users can request proposals only for images in their own workspace.
- A re-encoded visual preview (at most 1280 pixels on its longest side), current display
  settings, prompt, and up to 12 conversation turns are sent to the selected provider. EXIF/GPS metadata,
  original radiometric files, and temperature matrices are not sent. Image pixels can
  still contain visible sensitive information; the dialog discloses the transfer.
- OpenAI Responses requests use `store:false`; provider retention terms still apply.
- The editor displays the destination provider/model before sending. If the provider
  changed since the editor opened, the request is rejected and the user must reopen it.
  Keys are header-only, origins are fixed, redirects are disabled, and there is no
  silent provider fallback. Anthropic uses Messages; Google uses generateContent.
- The model proposes validated polygons and display parameters, never generated imagery
  or executable operations. Self-crossing/out-of-range polygons are rejected.
- Only one request per user and three per API process may run concurrently. Requests
  have a 70-second provider timeout and bounded input/output. Closing cancels the browser
  request, but an upstream request already sent may still finish and consume API usage.
- Original pixels, calibrated matrices, and analysis parameters are unchanged. Masks
  recolor the background in muted blue (scene texture retained) or conceal it in black,
  without inpainting/reconstruction. Blue does not mean zero temperature or correct
  reflected radiation. Exports retain source dimensions and include processing disclosure in PNG metadata.
  Focus readings exclude background pixels. Original full-frame readings remain available;
  for additional independent regions, use a measurement region to restrict readings.
- DJI SDK continues to handle radiometric decoding and available official palette LUTs.
  AI interpretation is a separate provider service; local OpenCV renders the display edits.
- AI outlines are approximate. Use the manual polygon and brushes for precise boundaries. No
  recovery of absent detail or diagnostic accuracy is promised.
- Chat text is held in browser memory for the current image, not stored in activity logs.
  The activity log records only that an AI proposal was requested. Applied settings and
  masks persist through the normal workspace/package workflow.

## Verification

Automated tests cover source/matrix preservation, mask rendering and serialization,
owner-only access, missing configuration, invalid proposals, no implicit saving,
provider request format, stripped metadata, and concurrent-request cleanup.
UI verification covers the supplied DJI M4T image, saved polygon and brush masks,
zoom, pan, undo/redo, preview/apply, and reopening. AI tests use a mocked provider;
live provider quality requires a configured key.

API references (reviewed 2026-10-10):

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [Anthropic structured outputs and schema limitations](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Anthropic vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Anthropic models](https://platform.claude.com/docs/en/models/overview)
- [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Gemini generateContent reference](https://ai.google.dev/api/generate-content)
- [Gemini models](https://ai.google.dev/gemini-api/docs/models)

## Suppress background heat colors without AI

The dialog always offers an independent manual workflow. Click **1. Outline the
insulator to keep**, then click ordered points around the target in the full image
(minimum three, maximum 256). **Undo selection** corrects the last click or brush stroke; **Redo selection** restores it. Click **2. Preview
blue background** and inspect the mask, then **3. Apply changes** in the fixed footer.
**Done** returns to the workspace; **Save draft** or **Save to inspection** persists it.
The preview itself does not change the workspace. Invalid outlines are rejected by
existing server validation. The existing focus area can be reused. AI suggestions and
chat input are hidden when no API key is configured, to avoid suggesting unavailable
edits. This manual workflow sends no image to an AI provider.

Background appearance in Enhance image offers muted blue, solid navy or darkening, with a suppression
strength slider. Manual blue previews leave insulator detail settings at zero to preserve
its existing colors. Stored settings without background_mode keep the prior darkening
behavior. AI proposals can recolor only specified mountain/cloud polygons as well as
recoloring everything outside a target outline.

## Precise mask editing and calibrated JPEGs

The **Insulator Focus** toolbar button opens the selection/preview dialog. Polygon, Add
brush, Erase brush, adjustable brush size, 1–6× zoom, Pan, Fit, undo/redo, clear, reset and
mask visibility let users retain fittings and remove heat between the discs. Coordinates
and brush radii are fractions of the source frame, independent of viewport size/zoom.
Brushed masks are refined in this editor rather than transformed with the old box handles.

The preset preserves original selected pixels by default, suppresses the background in
navy blue, and uses narrow outward feathering. **Enhance image → Insulator focus** provides
original-pixel preservation, subtle bounded local brightness/contrast/gamma/denoise/
sharpening, background strength, solid navy or contextual blue, and edge feathering.
**Insulator Auto Range** explicitly switches to a calibrated palette and derives both
endpoints from valid temperatures in the exact mask. It releases original-color preservation.
Global full-frame data, saved independent measurement regions and source files are unchanged.

Original DJI radiometric JPEGs are decoded by the existing SDK regardless of filename.
The user's two M4T samples (1280×1024 JPEG, 640×512 matrix) decode with SDK 1.8. Exported
JPEGs can lose that payload: their visual editing remains available, but readings, palettes
and auto range require a valid matrix. No values are inferred from RGB. The provided
version-1 .thermalpkg without a matrix reopens in visual-only mode.

**Enhanced PNG · full resolution** exports the full source dimensions without annotations
or crop. **Report image** includes the existing annotations and optional crop, at source
resolution. Both add processing metadata without padding the image. **Untouched original**
downloads original bytes. Editable packages retain the original, brush strokes, precise
mask geometry, enhancement settings and matrix when present. Existing packages remain
readable. Version 1 is unchanged because new optional settings have legacy defaults.

Assisted chat selection requires an administrator's configured AI provider key; manual
selection does not transmit images to an AI provider.
