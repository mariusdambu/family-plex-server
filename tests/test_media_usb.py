import unittest,sys,types,importlib.util,contextlib
from unittest.mock import patch,MagicMock
import pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import media_usb as m

class Tests(unittest.TestCase):
 def setUp(self):
  self.config=patch.object(m,'load',return_value={'usb_uuid':'ABCD-1234','usb_root':'/srv/family-plex-usb/disk','usb_filesystem':'exfat','usb_hotplug':True,'plex_uid':1000,'plex_gid':100});self.config.start();self.addCleanup(self.config.stop)
  self.lock=patch.object(m,'operation_lock',return_value=contextlib.nullcontext());self.lock.start();self.addCleanup(self.lock.stop)
 def test_force_requires_confirmation(self):
  with patch.object(m,'command') as run:
   with self.assertRaises(ValueError):m.operate('force-eject')
   run.assert_not_called()
 def test_unknown_action(self):
  with self.assertRaises(ValueError):m.operate('anything')
 def test_normal_busy_playback_does_not_stop_plex(self):
  with patch.object(m,'mounted',return_value=True),patch.object(m,'plex_running',return_value=True),patch.object(m,'usb_sessions',return_value=True),patch.object(m,'command') as run:
   with self.assertRaises(RuntimeError):m.operate('eject')
   run.assert_not_called()
 def test_force_stops_only_plex_and_restarts_after_unmount(self):
  with patch.object(m,'mounted',return_value=True),patch.object(m,'plex_running',return_value=True),patch.object(m.os.path,'ismount',return_value=False),patch.object(m,'command',return_value='') as run:
   result=m.operate('force-eject',True)
   self.assertTrue(result['safe_to_remove'])
   self.assertEqual([c.args[0] for c in run.call_args_list],[['docker','stop','--time','30','plex'],['sync','-f',m.mount_path()],['umount',m.mount_path()],['docker','start','plex']])
 def test_busy_unmount_still_restarts_plex_and_does_not_claim_safe(self):
  def command(args,**kwargs):
   if args[0]=='umount':raise RuntimeError('target is busy')
  with patch.object(m,'mounted',return_value=True),patch.object(m,'plex_running',return_value=True),patch.object(m,'command',side_effect=command) as run:
   with self.assertRaisesRegex(RuntimeError,'busy'):m.operate('force-eject',True)
   self.assertEqual(run.call_args.args[0],['docker','start','plex'])
 def test_normal_eject_keeps_plex_running(self):
  with patch.object(m,'mounted',return_value=True),patch.object(m,'plex_running',return_value=True),patch.object(m,'usb_sessions',return_value=False),patch.object(m.os.path,'ismount',return_value=False),patch.object(m,'container_mounted',return_value=False),patch.object(m,'command',return_value='') as run:
   self.assertTrue(m.operate('eject')['safe_to_remove'])
   self.assertFalse(any(c.args[0][0]=='docker' for c in run.call_args_list))
 def test_connect_does_not_restart_without_confirmation(self):
  with patch.object(m.os.path,'exists',return_value=True),patch.object(m,'mounted',return_value=True),patch.object(m,'visible',return_value=False),patch.object(m,'command',return_value='') as run:
   self.assertTrue(m.operate('connect')['needs_restart'])
   self.assertEqual(run.call_count,1)
 def test_other_mount_is_never_unmounted(self):
  with patch.object(m,'mounted',return_value=False),patch.object(m.os.path,'ismount',return_value=True),patch.object(m,'command') as run:
   with self.assertRaises(RuntimeError):m.operate('force-eject',True)
   run.assert_not_called()
 def test_stale_container_mount_is_not_reported_safe(self):
  with patch.object(m,'mounted',return_value=False),patch.object(m.os.path,'ismount',return_value=False),patch.object(m,'plex_running',return_value=True),patch.object(m,'container_mounted',return_value=True):
   with self.assertRaises(RuntimeError):m.operate('eject')
 def test_mount_verifies_uuid_and_exfat(self):
  for text,expected in [('ABCD-1234 exfat',True),('DIFFERENT exfat',False),('ABCD-1234 ext4',False)]:
   with patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=text)):
    self.assertEqual(m.mounted(),expected)

if __name__=='__main__':unittest.main(verbosity=2)
