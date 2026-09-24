"""Descriptive supplied sample context and paired quantitative measurements."""
from collections import defaultdict
import math
import importlib.util
import html
from .review_stage import execute,table,unique,report

def context(samples,observations):
    by_id=unique(samples,'sample_id')
    seen=set(); groups=defaultdict(lambda: {'present':0,'absent':0,'unknown':0})
    for row in observations:
        key=(row['sample_id'],row['feature_id'])
        if key in seen or row['sample_id'] not in by_id: raise ValueError('Duplicate observation or unknown sample')
        seen.add(key)
        if row['detection'] not in {'present','absent','unknown'}: raise ValueError('Invalid detection')
    lookup={(r['sample_id'],r['feature_id']):r['detection'] for r in observations}
    features=sorted({r['feature_id'] for r in observations})
    if len(samples)*len(features)>100_000: raise ValueError('Context matrix exceeds 100,000 cells')
    for s in samples:
        for feature in features:
            key=(feature,s['study_id'],s['laboratory'],s['country'],s['lane'],s['control_status'],s['library_molecule'],s['strand'])
            groups[key][lookup.get((s['sample_id'],feature),'unknown')]+=1
    keys=('feature_id','study_id','laboratory','country','lane','control_status','library_molecule','strand')
    return [{**dict(zip(keys,key)),**counts} for key,counts in sorted(groups.items())]

def run_context(samples,observations,output):
    def produce(paths,directory):
        samples=table(paths['samples'],('sample_id','study_id','laboratory','country','lane','control_status','control_source','library_molecule','strand'))
        for row in samples:
            if row['control_status'] not in {'negative','positive','technical','unknown'}: raise ValueError('Invalid control_status')
            if row['control_status']!='unknown' and row['control_source']=='unknown': raise ValueError('Control labels need an explicit evidence source')
            if row['library_molecule'] not in {'RNA','DNA','mixed','unknown'} or row['strand'] not in {'forward','reverse','unstranded','unknown'}: raise ValueError('Invalid assay/strand label')
        rows=context(samples,table(paths['observations'],('sample_id','feature_id','detection')))
        return report(directory,'Supplied study context',{'strata':rows},['All context and control labels are supplied evidence, not inferred from detection.','Unknown context is retained. Shared geography/laboratory/lane does not prove contamination or independence.','Missing observations are unknown; stratification is descriptive and never a rejection rule.'])
    return execute('context-v1',{'samples':samples,'observations':observations},output,__file__,produce)

def correlate(rows):
    groups=defaultdict(list); seen=set()
    for row in rows:
        key=(row['sample_id'],row['feature_id'])
        if key in seen: raise ValueError('Duplicate quantitative sample/feature')
        seen.add(key)
        pair=[]
        for field in ('x','y'):
            value=None if row[field]=='unknown' else float(row[field])
            if value is not None and not math.isfinite(value): raise ValueError('Non-finite measurement')
            pair.append(value)
        groups[(row['feature_id'],row['study_id'],row['assay'],row['x_unit'],row['y_unit'])].append(pair)
    result=[]
    for key,values in sorted(groups.items()):
        complete=[(x,y) for x,y in values if x is not None and y is not None]
        coefficient=None; reason='insufficient_pairs'
        if len(complete)>=3:
            # Scale first to avoid overflow for finite values with large magnitude.
            sx=max(abs(x) for x,y in complete) or 1; sy=max(abs(y) for x,y in complete) or 1
            xs=[x/sx for x,y in complete];ys=[y/sy for x,y in complete]
            mx=sum(xs)/len(xs);my=sum(ys)/len(ys)
            xx=sum((x-mx)**2 for x in xs);yy=sum((y-my)**2 for y in ys)
            reason='constant_measurement'
            if xx and yy:
                coefficient=max(-1,min(1,sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(xx*yy)));reason='descriptive_only'
        result.append({**dict(zip(('feature_id','study_id','assay','x_unit','y_unit'),key)),'complete_pairs':len(complete),'missing_pairs':len(values)-len(complete),'pearson_r':coefficient,'status':reason})
    return result

def run_quantitative(measurements,output):
    plotting=None
    if importlib.util.find_spec('matplotlib'):
        import matplotlib
        plotting=matplotlib.__version__
    def produce(paths,directory):
        supplied=table(paths['measurements'],('sample_id','feature_id','study_id','assay','x_unit','y_unit','x','y'))
        rows=correlate(supplied)
        files=report(directory,'Supplied quantitative associations',{'associations':rows},['No normalization or units are inferred; differing studies, assays and units are kept separate.','Pearson r describes supplied paired values; no significance, causality, helper dependence or ranking is inferred.','At least three complete pairs and nonconstant values are required. Missing values are not zeros.', 'Scatter plots use matplotlib '+plotting if plotting else 'Optional scatter plots unavailable: install the plots extra. Numerical output is complete.'])
        if plotting:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            groups=defaultdict(list)
            for row in supplied:
                key=tuple(row[k] for k in ('feature_id','study_id','assay','x_unit','y_unit'))
                if row['x']!='unknown' and row['y']!='unknown':groups[key].append((float(row['x']),float(row['y'])))
            images=[]
            for index,(key,pairs) in enumerate(sorted(groups.items())[:12]):
                pairs=pairs[:2000]
                sx=max(abs(x) for x,y in pairs) or 1;sy=max(abs(y) for x,y in pairs) or 1
                fig=Figure(figsize=(6,4));FigureCanvasAgg(fig);ax=fig.subplots()
                ax.scatter([x/sx for x,y in pairs],[y/sy for x,y in pairs],s=12)
                ax.set_xlabel('x / '+format(sx,'.6g')+' ['+key[3][:60]+']')
                ax.set_ylabel('y / '+format(sy,'.6g')+' ['+key[4][:60]+']')
                ax.set_title(' / '.join(key[:3])[:100]);fig.tight_layout()
                name='scatter-'+str(index)+'.svg';fig.savefig(directory/name,format='svg');files.append(name)
                images.append('<p>'+html.escape(' / '.join(key))+'</p><img alt="Supplied paired measurements" src="'+name+'">')
            with (directory/'report.html').open('a',encoding='utf-8') as target:target.write('<h2>Descriptive scatter plots</h2><p>First 12 strata; first 2,000 complete pairs per stratum. Axes scaled explicitly for numeric stability. No fit or inference.</p>'+''.join(images))
        return files
    return execute('quantitative-v2:plots='+str(plotting),{'measurements':measurements},output,__file__,produce)
