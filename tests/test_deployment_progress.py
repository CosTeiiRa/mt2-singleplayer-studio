import unittest
from metin2_studio import deployment_progress as progress


class DeploymentProgressTests(unittest.TestCase):
    def test_validation_has_no_restart_or_database_stages(self):
        job = {'status':'running'}
        progress.prepare(job,validation=True)
        self.assertEqual([s['id'] for s in job['progress']['steps']],['build','sources'])
        progress.enter(job,'build'); progress.enter(job,'sources'); job['status']='validated'; progress.finish(job)
        self.assertTrue(all(s['status']=='complete' for s in job['progress']['steps']))
        self.assertGreater(job['finished'],0)

    def test_failed_migration_cannot_mark_restart_or_health_as_complete(self):
        job = {'status':'running'}; progress.prepare(job,crafting=True)
        for stage in ('build','database','stop','migration'):
            progress.enter(job,stage)
        progress.enter(job,'migration')
        job['status']='failed'; progress.finish(job)
        states={s['id']:s['status'] for s in job['progress']['steps']}
        self.assertEqual(states['migration'],'failed')
        self.assertEqual(states['build'],'complete')
        self.assertEqual(states['restart'],'blocked')
        self.assertEqual(states['crafting'],'blocked')

    def test_native_update_exposes_one_launcher_stage_without_inventing_its_internal_progress(self):
        job={}; progress.prepare(job,native_update=True)
        self.assertEqual([s['id'] for s in job['progress']['steps']],['launcher','sources','health','content'])
        self.assertEqual(progress.command_stage(['powershell.exe','-File','launcher.ps1']),'launcher')

    def test_unverified_health_stays_warning_and_content_is_not_claimed(self):
        job={'status':'running'}; progress.prepare(job); progress.enter(job,'health')
        job['status']='unverified'; progress.finish(job)
        states={s['id']:s['status'] for s in job['progress']['steps']}
        self.assertEqual(states['health'],'warning'); self.assertEqual(states['content'],'blocked')

    def test_real_command_shapes_map_to_specific_observed_stages(self):
        for cmd,stage in [(['docker','compose','build','game'],'build'),
                          (['docker','compose','up','-d','--wait','mariadb'],'database'),
                          (['docker','compose','stop','game'],'stop'),
                          (['docker','compose','wait','playerbot-migrate'],'migration'),
                          (['studio','native-crafting'],'crafting'),
                          (['docker','compose','up','-d','--no-deps','--force-recreate','game'],'restart')]:
            with self.subTest(cmd=cmd): self.assertEqual(progress.command_stage(cmd),stage)
