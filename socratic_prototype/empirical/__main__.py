"""Import, fit and evaluate the Irena handover without modifying source files."""
import argparse
from pathlib import Path
from .pipeline import build,export,simulate_baseline,check_recovery,write


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    b=commands.add_parser('build',help='Create a new frozen 62-person reconstruction/evaluation bundle')
    b.add_argument('--source-dir',default='git_Irena');b.add_argument('--output-dir',required=True)
    b.add_argument('--mab-random-starts',type=int,default=24)
    e=commands.add_parser('export',help='Select actors for the ordinary five-condition simulator or calibration seeder')
    e.add_argument('--cohort-dir',required=True);e.add_argument('--output',required=True)
    e.add_argument('--split',choices=['all','development','evaluation'],default='development')
    e.add_argument('--source-id',action='append');e.add_argument('--fit-role',choices=['full','training'],default='full')
    e.add_argument('--offer-sensitivity',type=float,default=0.)
    f=commands.add_parser('baseline',help='Fresh full-protocol unassisted behavioural checks')
    f.add_argument('--cohort-dir',required=True);f.add_argument('--output',required=True)
    f.add_argument('--split',choices=['all','development','evaluation'],default='development')
    f.add_argument('--repeats',type=int,default=10);f.add_argument('--seed',default='empirical-baseline')
    f.add_argument('--offer-sensitivity',type=float,default=0.)
    r=commands.add_parser('recover',help='Internal parameter/policy recovery under the specified actor models')
    r.add_argument('--cohort-dir',required=True);r.add_argument('--output',required=True)
    r.add_argument('--split',choices=['all','development','evaluation'],default='development')
    r.add_argument('--source-id',action='append');r.add_argument('--repeats',type=int,default=1);r.add_argument('--seed',default='empirical-recovery')
    args=parser.parse_args()
    if args.command=='build':
        registry=build(args.source_dir,args.output_dir,args.mab_random_starts)
        print('Built',len(registry['people']),'researcher-side profiles in',args.output_dir)
    elif args.command=='export':
        actors=export(args.cohort_dir,args.split,args.source_id,args.fit_role,args.offer_sensitivity)
        write(args.output,actors);print('Exported',len(actors),'synthetic actors to',args.output)
    elif args.command=='baseline':
        result=simulate_baseline(args.cohort_dir,args.split,args.repeats,args.seed,args.offer_sensitivity)
        write(args.output,result);print('Wrote',len(result['runs']),'fresh full-protocol runs to',args.output)
    else:
        result=check_recovery(args.cohort_dir,args.split,args.repeats,args.seed,args.source_id)
        write(args.output,result);print('Wrote',len(result['results']),'internal recovery checks to',args.output)


if __name__=='__main__':main()
