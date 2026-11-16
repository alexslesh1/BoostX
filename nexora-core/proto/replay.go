package proto

const replayBits = 1024

// ReplayWindow accepts each counter at most once and rejects anything more
// than replayBits behind the highest counter seen, so a captured datagram
// can't be replayed while UDP reordering within the window still works.
type ReplayWindow struct {
	top  uint64
	bits [replayBits / 64]uint64
}

func (w *ReplayWindow) isSet(counter uint64) bool {
	i := counter % replayBits
	return w.bits[i/64]&(1<<(i%64)) != 0
}

func (w *ReplayWindow) set(counter uint64) {
	i := counter % replayBits
	w.bits[i/64] |= 1 << (i % 64)
}

func (w *ReplayWindow) clear(counter uint64) {
	i := counter % replayBits
	w.bits[i/64] &^= 1 << (i % 64)
}

// Check reports whether counter would be accepted, without recording it:
// it must only be recorded once the datagram has authenticated.
func (w *ReplayWindow) Check(counter uint64) bool {
	if counter == 0 {
		return false
	}
	if counter > w.top {
		return true
	}
	if w.top-counter >= replayBits {
		return false
	}
	return !w.isSet(counter)
}

// Mark records counter; false means it was already seen or is too old.
func (w *ReplayWindow) Mark(counter uint64) bool {
	if !w.Check(counter) {
		return false
	}
	if counter > w.top {
		if counter-w.top >= replayBits {
			w.bits = [replayBits / 64]uint64{}
		} else {
			for c := w.top + 1; c < counter; c++ {
				w.clear(c)
			}
		}
		w.top = counter
		w.clear(counter)
	}
	w.set(counter)
	return true
}
