# Core Patch Required: Multimodal Image Support for Event-Triggered Tasks

**File:** `core/continuity/executor.py`  
**Added by:** leona_discord plugin (2026-06-13)  
**Reason:** When `image_enabled=False` in the Discord plugin, images should be sent
directly to the multimodal model as content blocks instead of text URL hints.

This patch is currently applied directly to `executor.py`. It needs to be merged
into the main codebase so it survives `git pull`.

---

## Change 1: `_format_event_data` (around line 142)

**What:** When event data contains `image_content_blocks`, return a multimodal
content-block list instead of a plain string.

**Before:**
```python
        # The trigger message itself — emphasized
        if sender:
            parts.append(f">>> {sender}: {text}")
        else:
            parts.append(f">>> {text}")
        return "\n".join(parts)
```

**After:**
```python
        # The trigger message itself — emphasized
        if sender:
            parts.append(f">>> {sender}: {text}")
        else:
            parts.append(f">>> {text}")
        text_content = "\n".join(parts)

        # Multimodal support: if the event carries image_content_blocks
        # (base64 image data from plugins like leona_discord), return a
        # content-block list instead of a plain string so the main model
        # can see the actual pixels.  Pattern matches _inject_tool_images.
        image_blocks = obj.get("image_content_blocks")
        if image_blocks and isinstance(image_blocks, list):
            return [{"type": "text", "text": text_content}] + image_blocks

        return text_content
```

**Note:** The method signature says `-> str` but now conditionally returns a list.
This is intentional and safe — `execution_context.py:_run_inner` already handles
`content` as either string or list (see `_inject_tool_images` pattern).

---

## Change 2: `run()` method (around line 175)

**What:** When `event_display` is a multimodal list, prepend task instructions
as a text block instead of string concatenating.

**Before:**
```python
        if event_data is not None:
            event_display = self._format_event_data(event_data)
            instructions = task.get("initial_message", "").strip()
            if instructions:
                task["initial_message"] = f"{instructions}\n\n{event_display}"
            else:
                task["initial_message"] = event_display
```

**After:**
```python
        if event_data is not None:
            event_display = self._format_event_data(event_data)
            instructions = task.get("initial_message", "").strip()
            if instructions:
                if isinstance(event_display, list):
                    # Multimodal: prepend instructions as a text block
                    task["initial_message"] = [{"type": "text", "text": instructions}] + event_display
                else:
                    task["initial_message"] = f"{instructions}\n\n{event_display}"
            else:
                task["initial_message"] = event_display
```

---

## Why this is needed

The Discord plugin collects image attachments and, when `image_enabled=False`
(native vision model), downloads them, base64-encodes them, and includes them
in the event payload as `image_content_blocks`:

```json
{
  "content": "User message text",
  "image_content_blocks": [
    {"type": "image", "media_type": "image/jpeg", "data": "<base64>"}
  ]
}
```

Without this patch, `_format_event_data` extracts only `content` as text, and
the multimodal blocks are silently discarded. The model sees text URL hints
instead of actual pixels.

With this patch, the blocks flow through to `ExecutionContext._run_inner` which
builds `{"role": "user", "content": [text_block, image_block, ...]}` — the same
pattern `_inject_tool_images` already uses for tool-returned images.

---

## Upstream compatibility

This follows the existing `_inject_tool_images` pattern in `core/chat/chat.py`.
No changes needed to `execution_context.py` — it already handles `content` as
either string or list.
