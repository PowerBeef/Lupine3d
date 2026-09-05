"""The quality budget cannot pass missing, mismatched or contaminated evidence."""
import copy
import unittest
from test_render_experiments import br
from evaluate_quality_budget import evaluate


def report(mean,p95,which='candidate'):
    return dict(schema='lupine3d.motion.v2',**{which+'_sha256':'hash'},cases={'walking':{which:dict(
        observation=dict(timing_unit='cpu_t_cycles',timing_reconciled=True,game_ram_writes_after_trial_start=0),
        input_replay_sha256='replay',lcd_frame_counter_delta=3584,
        full_frame_cycles=dict(mean=mean,p95=p95,count=500),full_geometry_updates_hz=9)}})


class BudgetTests(unittest.TestCase):
    def test_both_metrics_use_half_gain_bound_inclusively(self):
        b,p=report(100,200,'baseline'),report(80,160)
        self.assertTrue(evaluate(b,p,report(90,180))['passed'])
        self.assertFalse(evaluate(b,p,report(90.01,180))['passed'])
        self.assertFalse(evaluate(b,p,report(90,180.01))['passed'])

    def test_replay_units_duration_and_diagnostic_writes_must_match(self):
        b,p,q=report(100,200,'baseline'),report(80,160),report(85,170)
        for key,value in (('input_replay_sha256','different'),('lcd_frame_counter_delta',144)):
            candidate=copy.deepcopy(q);candidate['cases']['walking']['candidate'][key]=value
            with self.assertRaises(ValueError):evaluate(b,p,candidate)
        for key,value in (('timing_unit','lcd_dots'),('timing_reconciled',False),('game_ram_writes_after_trial_start',1)):
            candidate=copy.deepcopy(q);candidate['cases']['walking']['candidate']['observation'][key]=value
            with self.assertRaises(ValueError):evaluate(b,p,candidate)
        q['cases']={}
        with self.assertRaises(ValueError):evaluate(b,p,q)


if __name__=='__main__':unittest.main()
