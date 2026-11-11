import unittest
from agent.short_episode_research import EpisodeEvent, step

class EpisodeResearchTests(unittest.TestCase):
    def test_repeated_structural_suppressed(self):
        e = EpisodeEvent('SHORT','ENTRY','SHORT:LIQUIDITY_SWEEP:100')
        action, state = step(None,e)
        self.assertEqual(action,'OPEN')
        self.assertEqual(step(state,e)[0],'SUPPRESS')

    def test_new_structure_rearms(self):
        _, state = step(None,EpisodeEvent('SHORT','ENTRY','SHORT:LIQUIDITY_SWEEP:100'))
        self.assertEqual(step(state,EpisodeEvent('SHORT','ENTRY','SHORT:LIQUIDITY_SWEEP:200'))[0],'OPEN')

    def test_legacy_after_structural_suppressed(self):
        _, state = step(None,EpisodeEvent('SHORT','ENTRY','SHORT:BREAKDOWN_RETEST:100'))
        self.assertEqual(step(state,EpisodeEvent('SHORT','ENTRY'))[0],'SUPPRESS')

    def test_long_unchanged(self):
        _, state = step(None,EpisodeEvent('LONG','ENTRY'))
        self.assertEqual(step(state,EpisodeEvent('LONG','ENTRY','SHORT:LIQUIDITY_SWEEP:200'))[0],'SUPPRESS')

    def test_bad_key_cannot_rearm(self):
        _, state = step(None,EpisodeEvent('SHORT','ENTRY'))
        self.assertEqual(step(state,EpisodeEvent('SHORT','ENTRY','SHORT:LIQUIDITY_SWEEP:bad'))[0],'SUPPRESS')

if __name__ == '__main__': unittest.main()
