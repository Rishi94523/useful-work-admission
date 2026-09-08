"""Whole-run identity adapter for the existing transactional campaign scheduler.

One-use credit is for assigned, previously uncompleted output coverage. It is not
a claim about the time the worker performed the computation or its identity.
"""
import hashlib,json,math
from research.docking_campaign import Campaign,canonical

class WholeRunCampaign(Campaign):
    def register(self,campaign,engine,receptor,ligand,input_hash,region,start,count,cap,cost):
        if type(start)!=int or type(count)!=int or start<0 or not 1<=count<=1024 or start+count>100000:
            raise ValueError('Invalid run range')
        if type(cap)!=int or not 1<=cap<=1000000 or not math.isfinite(cost) or cost<=0:raise ValueError('Invalid bounded search')
        spec={'model_version':engine,'receptor':receptor,'ligand':ligand,'conformer_bank':input_hash,'region':region,'search_parameters':{'method':'Vina1.2.7-direct-seed-single-thread-no-refine','seed_base':104729,'seed_stride':13007,'cap':cap}}
        # Model/inputs/seed-range identity excludes the budget and campaign label.
        # Reject nested-budget reuse rather than charging the shared prefix twice.
        base={**spec,'search_parameters':{k:v for k,v in spec['search_parameters'].items() if k!='cap'}}
        family=hashlib.sha256(canonical(base)).hexdigest();task=hashlib.sha256(canonical([family,start,count,cap])).hexdigest()
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM units WHERE family=? AND start<? AND stop>?',(family,start+count,start)).fetchone():raise ValueError('Previously registered scientific seeds, including other budgets')
            db.execute('INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?)',(task,family,campaign,ligand,start,start+count,cost,canonical(spec).decode(),'UNASSIGNED',None,None))
        return task

    @staticmethod
    def units(lease):
        result=[]
        for task in lease['tasks']:
            spec=task['spec'];p=spec['search_parameters']
            for i in range(task['start'],task['start']+task['count']):
                result.append({'ligand':spec['ligand'],'input':spec['conformer_bank'],'seed':p['seed_base']+p['seed_stride']*i,'cap':p['cap'],'engine':spec['model_version'],'run':i})
        return result

    @staticmethod
    def flat_draws(lease,challenge):
        offsets=[];n=0
        for t in lease['tasks']:offsets.append(n);n+=t['count']
        return [offsets[j]+i for j,i in challenge['draws']]
