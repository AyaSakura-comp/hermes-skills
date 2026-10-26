import importlib.util
import pathlib
import unittest
p=pathlib.Path(__file__).with_name('photo_edit.py')

class Tests(unittest.TestCase):
    def test_runner_exists(self):
        self.assertTrue(p.exists(), 'Dedicated editing CLI missing')
    def test_graph_and_errors(self):
        if not p.exists(): self.fail('Dedicated editing CLI missing')
        spec=importlib.util.spec_from_file_location('editor',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        w=m.workflow('folder/input.png','edit',42,25,0)
        self.assertEqual(w['4']['inputs']['images.image_1'],['9',0])
        self.assertEqual(w['6']['inputs']['latent_image'],['4',2])
        self.assertEqual(w['4']['inputs']['clip'],['2',0])
        self.assertNotIn('5',w)
        self.assertEqual(m.completed_images({}),[])
        with self.assertRaises(RuntimeError):m.submitted({'error':'bad graph'})
        with self.assertRaises(RuntimeError):m.completed_images({'status':{'status_str':'error','messages':['failed']}})
        self.assertEqual(m.submitted({'prompt_id':'valid'}),'valid')

class ResizeTests(unittest.TestCase):
    def test_resize(self):
        spec=importlib.util.spec_from_file_location('editor',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        self.assertTrue(hasattr(m,'prepare_image'),'Image pre-resize missing')
        from PIL import Image
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src=pathlib.Path(d)/'source.png';out=pathlib.Path(d)/'prepared.png'
            for size,expected in [((2160,2160),(1080,1080)),((2400,1600),(1080,720)),((1600,2400),(720,1080)),((640,480),(640,480))]:
                Image.new('RGB',size).save(src)
                meta=m.prepare_image(src,out,1080)
                self.assertEqual(Image.open(out).size,expected)
                self.assertEqual(Image.open(src).size,size)
            meta=m.prepare_image(src,out,0)
            self.assertEqual(Image.open(out).size,(640,480))

if __name__=='__main__':unittest.main()
