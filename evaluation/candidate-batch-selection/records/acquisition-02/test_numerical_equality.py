import unittest
import numpy as np
from acquisition import sample_latent, fractional_top_membership
class NumericalEquality(unittest.TestCase):
    def test_blas_duplicate_counterexample_repaired(self):
        rng=np.random.default_rng(123);factor=rng.normal(size=(194,5));factor[-1]=factor[0]
        state=rng.bit_generator.state;mean=np.full(194,-1000.);mean[[0,193]]=0
        old=mean+rng.standard_normal((128,5))@factor.T
        rng.bit_generator.state=state;new=sample_latent(mean,factor,[[0,193]],rng,128)
        np.testing.assert_array_equal(new[:,0],new[:,193])
        winners=new==new.max(axis=1)[:,None]
        self.assertTrue(winners[:,0].all() and winners[:,193].all())
        boundary=np.column_stack([np.full((128,9),1000.),new[:,[0,193]]])
        np.testing.assert_array_equal(fractional_top_membership(boundary,10)[:,-2:],np.full((128,2),.5))
        self.assertTrue(np.max(abs(old[:,0]-old[:,193]))<1e-12)
    def test_no_group_draws_and_rng_state_identical(self):
        factor=np.arange(21,dtype=float).reshape(7,3)/10;mean=np.arange(7.)
        r1=np.random.default_rng(91);r2=np.random.default_rng(91)
        np.testing.assert_array_equal(sample_latent(mean,factor,[],r1,8192),mean+r2.standard_normal((8192,3))@factor.T)
        self.assertEqual(r1.bit_generator.state,r2.bit_generator.state)
    def test_multiple_groups_and_zero_rank(self):
        means=np.array([2.,1.,2.,1.]);factor=np.empty((4,0));rng=np.random.default_rng(12)
        s=sample_latent(means,factor,[[0,2],[1,3]],rng,8192)
        np.testing.assert_array_equal(s,np.broadcast_to(means,s.shape))
    def test_noise_is_added_after_latent_copy(self):
        latent=sample_latent(np.ones(3),np.ones((3,1)),[[0,1,2]],np.random.default_rng(3),8192)
        observed=latent+np.random.default_rng(4).normal(size=latent.shape)*.2
        np.testing.assert_array_equal(latent[:,0],latent[:,1]);self.assertFalse(np.array_equal(observed[:,0],observed[:,1]))
if __name__=='__main__':unittest.main(verbosity=2)
