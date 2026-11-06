"""Test-only source clock fence and credential-free failure diagnostics."""
import time
import traceback

CHECKS={'preprocessing_presence_mismatch','source_clock_regressed','source_clock_not_advanced'}


def wait_next_second(previous, clock=time.time, monotonic=time.monotonic, pause=time.sleep, timeout=3):
    """Never submit a control in a second used by an earlier source sample.

    This is a real-clock fence, not a future timestamp or wider processing wait.
    A clock that stops/regresses fails boundedly; it cannot fabricate freshness.
    """
    if (type(previous) is not int or previous < 0 or type(timeout) not in (int,float)
            or not 0 < timeout <= 3):
        raise ValueError('Invalid test source-clock fence')
    deadline=monotonic()+timeout
    while True:
        current=int(clock())
        if current > previous:return current
        if monotonic() >= deadline:raise TimeoutError('source_clock_not_advanced')
        pause(0.02)


def public_failure_report(value):
    """Allowlisted metadata only: no messages, commands, URLs, tokens or values."""
    kinds={'AssertionError','TimeoutError','TimeoutExpired','ValueError','TypeError',
           'KeyError','RuntimeError','HTTPError','ConnectionError','ReadTimeout','OSError'}
    files={'functional-platform.py','functional_windows_service_policy.py','wsp_ci_observation.py'}
    if not isinstance(value,dict):value={}
    kind=value.get('exception')
    result={'result':'FAIL','exception':kind if isinstance(kind,str) and kind in kinds else 'Exception','frames':[]}
    check=value.get('check')
    if isinstance(check,str) and check in CHECKS:result['check']=check
    frames=value.get('frames',[])
    if not isinstance(frames,list):frames=[]
    for frame in frames[:8]:
        if (isinstance(frame,dict) and isinstance(frame.get('file'),str) and frame['file'] in files and
                type(frame.get('line')) is int and 1 <= frame['line'] <= 10000):
            result['frames'].append({'file':frame['file'],'line':frame['line']})
    return result


def failure_report(error):
    frames=[{'file':f.filename.replace('\\','/').rsplit('/',1)[-1],'line':f.lineno}
            for f in traceback.extract_tb(error.__traceback__)]
    check=error.args[0] if len(error.args)==1 and isinstance(error.args[0],str) else None
    return public_failure_report({'exception':type(error).__name__,'frames':frames,'check':check})
