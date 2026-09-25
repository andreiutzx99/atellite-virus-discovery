"""Harmless CLI fixture used to demonstrate external-tool adapters."""
import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='Copy text with a fixture prefix')
    parser.add_argument('--version', action='version', version='fixture-transform 1.0')
    parser.add_argument('source')
    parser.add_argument('destination')
    parser.add_argument('prefix')
    args = parser.parse_args(argv)
    try:
        source = Path(args.source).read_text(encoding='utf-8')
        Path(args.destination).write_text(args.prefix+source, encoding='utf-8')
    except (OSError, UnicodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print('fixture text transform complete')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())