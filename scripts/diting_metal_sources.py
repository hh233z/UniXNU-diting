"""The prepared translator contract consumed by Diting's 22H374 bridge."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = '624bab3918de5b978e1101517abca2b4fa426565'
PATCH_DIRECTORY = ROOT / 'patches/metal2vulkan/parity114'


def validate_parity_sources(translator: Path, guest: str) -> dict:
    """Reject an unprepared or mismatched modern tree before invoking Xcode."""
    if guest != '22H374':
        raise ValueError('the pinned modern translator supports only guest 22H374')
    metadata = json.loads((translator / '.diting-parity.json').read_text(encoding='utf-8'))
    patches = [p.name for p in sorted(PATCH_DIRECTORY.glob('*.patch'))]
    if (metadata.get('translator') != PIN or metadata.get('guest') != guest
            or metadata.get('patches') != patches):
        raise ValueError('translator pin, guest or patch series differs; prepare a fresh tree')
    # These are the interfaces used by NativeMetalObjects.rs, not the removed
    # MetalLevel / trim_empty_blocks interfaces from the legacy source family.
    runtime = translator / 'crates/metal2vulkan-runtime/src'
    required = {
        'pixel_format_info.rs': ['ios_format_info(raw,645)'],
        'device/mod.rs': ['pub fn release_kept_memory('],
        'rebind.rs': ['pub fn refuse_rebinds('],
        'lib.rs': ['pub mod stage_trace;'],
        'stage_trace.rs': ['pub fn enable_timeline(', 'pub fn set_diagnostic_hook('],
        'command_buffer/mod.rs': ['pub fn diagnostic_id(', 'pub fn stage_summary('],
    }
    for relative, markers in required.items():
        text = (runtime / relative).read_text(encoding='utf-8')
        for marker in markers:
            if marker not in text:
                raise ValueError(f'missing prepared runtime interface in {relative}: {marker}')
    return metadata
