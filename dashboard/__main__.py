"""Create a local report; never overwrite a prior file implicitly."""
import argparse
from pathlib import Path
from dashboard.scenarios import load_scenario, save_scenario
from dashboard.report import render
from demo_portfolio import scenario as demo_scenario


def main():
    parser = argparse.ArgumentParser(description='Debt Shredder local scenario report')
    parser.add_argument('--scenario', type=Path, help='Saved scenario; otherwise use the synthetic example')
    parser.add_argument('--output', required=True, type=Path, help='New HTML report file')
    parser.add_argument('--save-inputs', type=Path, help='Also save inputs to a new scenario file')
    args = parser.parse_args()
    scenario = load_scenario(args.scenario) if args.scenario else demo_scenario()
    html = render(scenario)
    if args.save_inputs:
        save_scenario(scenario, args.save_inputs)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    print(f'Local report saved: {args.output}')


if __name__ == '__main__':
    main()
