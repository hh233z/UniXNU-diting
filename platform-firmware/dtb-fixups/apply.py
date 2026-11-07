#!/usr/bin/env python3
"""Bake the diting PCIe/Wi-Fi fixups into the live device tree dump.

The live tree names the Wi-Fi enable/reset/wake lines differently from the Pong
baseline the recipe was written against, and its PCIe refgen clock sits at another
index. The values below are the ones the device itself reports.
"""
import argparse
from pathlib import Path

PROPS = (
    'wlan-enable-gpios = <0x3c 0x50 0x00>;',   # wlan-en-gpio, TLMM 80
    'reset-gpios = <0x3c 0x5e 0x00>;',         # perst-gpio, TLMM 94
    'clkreq-gpios = <0x3c 0x5f 0x00>;',        # pcie0_clkreqn mux, TLMM 95
    'wake-gpios = <0x3c 0x60 0x00>;',          # wake-gpio, TLMM 96
    'xo-clk-gpios = <0x3c 0xcc 0x00>;',        # CNSS qcom,xo-clk-gpio, TLMM 204
)
MEMORY = ('	memory@80000000 {
		device_type = "memory";
'
          '		reg = <0x00 0x80000000 0x03 0x00>;
	};

')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    lines = args.input.read_text().split('
')
    out, patched = [], 0
    for line in lines:
        if any(line.strip() == prop for prop in PROPS):
            continue
        out.append(line)
        if line.strip() == 'compatible = "qcom,pci-msm";':
            out.extend('			' + prop for prop in PROPS)
            patched += 1
    text = '
'.join(out)
    if 'memory@80000000' not in text:
        text = text.replace('	chosen {', MEMORY + '	chosen {', 1)
    assert patched > 0, 'no qcom,pci-msm node in the input tree'
    args.output.write_text(text)
    print('pci-msm nodes patched:', patched)


if __name__ == '__main__':
    main()
