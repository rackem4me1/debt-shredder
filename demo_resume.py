"""Synthetic save/restart example. Files are created only in the supplied directory."""
import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from demo_promotions import scenario
from engine.simulation import simulate_revolving,resume_revolving
from engine.checkpoint_io import save_debt_checkpoint,load_debt_checkpoint


def run(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    account,cycles,minimum,transition=scenario()
    partial=simulate_revolving(account,date(2026,1,1),date(2026,1,3),cycles,minimum,(),lambda *args:Decimal(0),
        promo_transitions=(transition,))
    path=directory/'debt_checkpoint.json'
    save_debt_checkpoint(partial.checkpoint,path)
    loaded=load_debt_checkpoint(path)
    decisions=[]
    def choose(view):
        decisions.append({'date':view.on.isoformat(),'effective_apr':str(view.segments[0].apr.value),
            'promo_exited':view.segments[0].promo_exited})
        return Decimal('50')
    resumed=resume_revolving(loaded,date(2026,1,31),(date(2026,1,4),),choose_decision=choose)
    full=simulate_revolving(account,date(2026,1,1),date(2026,1,31),cycles,minimum,(date(2026,1,4),),None,
        choose_decision=lambda view:Decimal('50'),promo_transitions=(transition,))
    if resumed!=full:raise AssertionError('resumed projection differs from full replay')
    return {'example':'Synthetic checkpoint saved at promo cutoff, then resumed with a $50 payment.',
        'saved_as_of':loaded.as_of.isoformat(),'ending_balance':str(resumed.account.total_balance()),
        'matches_uninterrupted':True,'promo_assessment_count':sum(a.kind=='promo_exit' for a in resumed.audit),
        'decisions':decisions}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args()
    result=run(args.directory)
    output=json.dumps(result,indent=2)+'\n'
    (Path(args.directory)/'RESUME_RESULTS.json').write_text(output)
    print(output)
