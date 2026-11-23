import unittest
from unittest.mock import patch
from parallel_browser import parallel_browser


class ParallelTests(unittest.TestCase):
    def test_invalid_tasks_never_reach_browser(self):
        for tasks in ([], [{}], [{'url':'file:///x','action':'read'}],
                      [{'page':1,'action':'click'}], [{'page':1,'action':'fill','ref':'e1'}],
                      [{'page':True,'action':'read'}], [{'page':1,'action':'read'}]*2,
                      [{'page':i,'action':'read'} for i in range(6)]):
            with self.subTest(tasks=tasks), patch('parallel_browser.neo_browser') as run:
                self.assertIn('error',parallel_browser({'tasks':tasks}))
                run.assert_not_called()

    def test_batch_runs_concurrently_and_escapes_page_data(self):
        with patch('parallel_browser.neo_browser',return_value={'ok':True}) as run:
            tasks=[{'url':'https://example.com/?q="hello"','action':'read'},
                   {'page':3,'action':'fill','ref':'e12','value':'hello\nworld'}]
            self.assertEqual(parallel_browser({'tasks':tasks}),{'ok':True})
            code=run.call_args.args[0]['code']
            self.assertIn('Promise.all(tasks.map',code)
            self.assertIn('hello\\nworld',code)
