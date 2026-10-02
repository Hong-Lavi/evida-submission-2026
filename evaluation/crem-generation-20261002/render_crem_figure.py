"""Render the fixed published counts; no molecule processing or model calls."""
from pathlib import Path
import csv,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path(__file__).resolve().parent

def main():
    s=json.loads((B/'crem-summary.json').read_text())['conditions']['900s_longer']
    with (B/'crem-per-task-metrics.csv').open(newline='') as f:rows=[r for r in csv.DictReader(f) if r['condition']=='900s_longer']
    fig,axs=plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[1.1,1.4]})
    fig.subplots_adjust(left=.14,right=.97,wspace=.48,bottom=.2,top=.84)
    colors={'completed':'#187d65','coordinator_interruption':'#bb7a30','timeout':'#b45454','global_deadline':'#b45454'}
    for i,row in enumerate(rows):
        axs[0].barh(i,1,color=colors.get(row['status'],'#777777'),height=.7)
        axs[0].text(.04,i,row['status'].replace('coordinator_interruption','interrupted'),va='center',fontsize=9,color='white')
    axs[0].set_yticks(range(len(rows)),[r['task'] for r in rows],fontsize=8);axs[0].invert_yaxis();axs[0].set_xticks([]);axs[0].set_xlim(0,1)
    axs[0].set_title(f"All 10 tasks: {s['native_returns_available']} completed",fontsize=11)
    labels=['Returned records','Valid structures','Unique connectivity','New vs 120 inputs','New vs full train','Exact source trace']
    keys=['returned_rows','returned_valid','returned_unique_connectivity','returned_novel_input_connectivity','returned_novel_train_connectivity','returned_exact_trace_matches']
    values=[s['returned'][k] for k in keys];axs[1].barh(range(6),values,color=['#364759','#187d65','#5e76a6','#5e76a6','#5e76a6','#187d65'])
    axs[1].set_yticks(range(6),labels,fontsize=9);axs[1].invert_yaxis();axs[1].set_xlim(0,max(values)*1.15)
    for i,v in enumerate(values):axs[1].text(v+max(values)*.015,i,str(v),va='center',fontsize=10)
    axs[1].set_title(f"{s['native_returns_available']} completed tasks; within-task sums",fontsize=11)
    axs[1].set_xlabel('Records / sum of within-task structure counts',fontsize=9)
    for ax in axs:ax.spines[['top','right']].set_visible(False)
    fig.suptitle('Native conditional CReM generation: completion and source traceability',fontsize=13)
    fig.text(.5,.045,'No activity, efficacy or synthetic success was measured. Interrupted tasks remain in the denominator.\n210-second condition: 0/10 native returns; longer condition uses a different concurrency budget.',ha='center',fontsize=9)
    for ext in ['png','svg','pdf']:fig.savefig(B/('crem-summary.'+ext),dpi=180)
    plt.close(fig)

if __name__=='__main__':main()
