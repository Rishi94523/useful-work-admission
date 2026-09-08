"""Whole-run identity adapter for the existing transactional campaign scheduler.

One-use credit is for assigned, previously uncompleted output coverage. It is not
a claim about the time the worker performed the computation or its identity.
"""
import hashlib,json,math
from research.docking_campaign import Campaign,canonical

class WholeRunCampaign(Campaign):
    def __init__(self,path,clock=None,max_credit_challenges=3):
        if type(max_credit_challenges)!=int or not 1<=max_credit_challenges<=16:raise ValueError('Invalid campaign attempt limit')
        if clock is None:super().__init__(path)
        else:super().__init__(path,clock)
        self.max_credit_challenges=max_credit_challenges
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS work_attempts(task TEXT PRIMARY KEY,challenges INTEGER NOT NULL DEFAULT 0,limit_count INTEGER NOT NULL)')

    def _lease_candidates(self,db,campaign):
        return db.execute("SELECT u.* FROM units u JOIN work_attempts a ON a.task=u.task WHERE u.campaign=? AND u.state IN ('UNASSIGNED','EXPIRED') AND a.challenges<a.limit_count ORDER BY RANDOM()",(campaign,)).fetchall()

    def _before_challenge(self,db,tasks):
        for task in tasks:
            changed=db.execute('UPDATE work_attempts SET challenges=challenges+1 WHERE task=? AND challenges<limit_count',(task['task'],)).rowcount
            if changed!=1:raise ValueError('Scientific work challenge budget exhausted')

    def register(self,campaign,engine,receptor,ligand,input_hash,region,start,count,cap,cost):
        if type(start)!=int or type(count)!=int or start<0 or not 1<=count<=1024 or start+count>100000:
            raise ValueError('Invalid run range')
        if type(cap)!=int or not 1<=cap<=1000000 or not math.isfinite(cost) or cost<=0:raise ValueError('Invalid bounded search')
        spec={'model_version':engine,'receptor':receptor,'ligand':ligand,'conformer_bank':input_hash,'region':region,'search_parameters':{'method':'Vina1.2.7-direct-seed-single-thread-no-refine','seed_base':104729,'seed_stride':13007,'cap':cap}}
        # Model/inputs/seed-range identity excludes the budget and campaign label.
        # Reject nested-budget reuse rather than charging the shared prefix twice.
        base={**spec,'search_parameters':{k:v for k,v in spec['search_parameters'].items() if k!='cap'}}
        base.pop('ligand') # display aliases cannot make identical molecular inputs new
        family=hashlib.sha256(canonical(base)).hexdigest();task=hashlib.sha256(canonical([family,start,count,cap])).hexdigest()
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM units WHERE family=? AND start<? AND stop>?',(family,start+count,start)).fetchone():raise ValueError('Previously registered scientific seeds, including other budgets')
            db.execute('INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?)',(task,family,campaign,ligand,start,start+count,cost,canonical(spec).decode(),'UNASSIGNED',None,None))
            db.execute('INSERT INTO work_attempts VALUES(?,0,?)',(task,self.max_credit_challenges))
        return task

    def recovery_queue(self):
        with self.transaction() as db:
            self._expire(db,self.clock())
            return [dict(r) for r in db.execute("SELECT u.task,u.start,u.stop,a.challenges,a.limit_count FROM units u JOIN work_attempts a ON a.task=u.task WHERE u.state='EXPIRED' AND a.challenges>=a.limit_count")]

    def record_validation(self,task,run_index,output_digest,status):
        """Trusted later science validation; never creates a new admission credit."""
        if status not in {'VERIFIED','REPAIRED','SUSPECT'} or len(output_digest)!=64 or any(c not in '0123456789abcdef' for c in output_digest):raise ValueError('Invalid validation record')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM units WHERE task=? AND state=?',(task,'COMPLETED')).fetchone()
            if not row or type(run_index)!=int or not row['start']<=run_index<row['stop']:raise ValueError('Validation requires a completed scientific unit')
            db.execute('CREATE TABLE IF NOT EXISTS scientific_validation(task TEXT,run_index INTEGER,status TEXT,output_digest TEXT,PRIMARY KEY(task,run_index))')
            db.execute('INSERT OR REPLACE INTO scientific_validation VALUES(?,?,?,?)',(task,run_index,status,output_digest))

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
