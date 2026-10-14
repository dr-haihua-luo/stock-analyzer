import sys, time
import needle
path = sys.argv[1]
whistle = needle.Whistle()
t = time.time()
out = whistle.transcribe(path)
print(type(out), out)
print(f"{(time.time() - t) * 1000:.0f} ms")
