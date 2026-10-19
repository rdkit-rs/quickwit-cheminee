use lru::LruCache;
use std::borrow::Borrow;
use std::num::NonZeroUsize;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::atomic::{AtomicBool, Ordering};

#[test]
fn panicking_key_drop_preserves_links_and_eviction() {
    static ARMED: AtomicBool = AtomicBool::new(false);
    #[derive(Hash, PartialEq, Eq)]
    struct Key(u32);
    impl Borrow<u32> for Key {
        fn borrow(&self) -> &u32 {
            &self.0
        }
    }
    impl Drop for Key {
        fn drop(&mut self) {
            if self.0 == 2 && ARMED.swap(false, Ordering::SeqCst) {
                panic!("intentional key destructor panic");
            }
        }
    }
    let mut cache = LruCache::new(NonZeroUsize::new(3).unwrap());
    for key in 1..=3 {
        cache.put(Key(key), key * 10);
    }
    ARMED.store(true, Ordering::SeqCst);
    assert!(catch_unwind(AssertUnwindSafe(|| cache.pop(&2u32))).is_err());
    assert_eq!(cache.len(), 2);
    assert!(!cache.contains(&2u32));
    assert_eq!(
        cache.iter().map(|(k, v)| (k.0, *v)).collect::<Vec<_>>(),
        vec![(3, 30), (1, 10)]
    );
    cache.put(Key(4), 40);
    cache.put(Key(5), 50); // Force eviction after the failed pop.
    assert!(!cache.contains(&1u32));
    assert_eq!(
        cache.iter().map(|(k, v)| (k.0, *v)).collect::<Vec<_>>(),
        vec![(5, 50), (4, 40), (3, 30)]
    );
    assert_eq!(cache.get(&3u32), Some(&30));
    assert_eq!(cache.pop(&4u32), Some(40));
    cache.clear();
    assert!(cache.is_empty());
}

#[test]
fn ordinary_operations_preserve_recency_and_replacement() {
    let mut cache = LruCache::new(NonZeroUsize::new(2).unwrap());
    assert_eq!(cache.put(1, 10), None);
    assert_eq!(cache.put(2, 20), None);
    assert_eq!(cache.get(&1), Some(&10));
    assert_eq!(cache.peek_lru(), Some((&2, &20)));
    assert_eq!(cache.put(1, 11), Some(10));
    cache.put(3, 30);
    assert!(!cache.contains(&2));
    assert_eq!(cache.pop(&1), Some(11));
    assert_eq!(cache.pop(&1), None);
    assert_eq!(cache.len(), 1);
}
