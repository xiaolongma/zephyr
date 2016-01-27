'''
Distribution wrappers for composite problems
'''

import numpy as np
from .discretization import DiscretizationWrapper

try:
    import multiprocessing
except ImportError:
    PARALLEL = False
else:
    PARALLEL = True

PARTASK_TIMEOUT = None

class BaseDist(DiscretizationWrapper):
    
    initMap = {
    #   Argument        Required    Rename as ...   Store as type
        'disc':         (True,      '_disc',        None),
        'parallel':     (False,     '_parallel',    bool),
        'nWorkers':     (False,     '_nWorkers',    np.int64),
        'remDists':     (False,     None,           list),
    }
    
    maskKeys = {'remDists'}
    
    @property
    def remDists(self):
        'Remaining distributor objects in the call graph'

        return getattr(self, '_remDists', [])
    @remDists.setter
    def remDists(self, value):
        if value:
            self._discOverride = value.pop(0)
        self._remDists = value
    
    @property
    def disc(self):
        'The discretization to instantiate'

        return getattr(self, '_discOverride', self._disc)
    
    @property
    def addFields(self):
        'Returns additional fields for the subProblem systemConfigs'

        return {'remDists': self.remDists}
    
    @property
    def systemConfig(self):
        self._systemConfig.update(self.remDists)
        return self._systemConfig
    @systemConfig.setter
    def systemConfig(self, value):
        self._systemConfig = value


class BaseMPDist(BaseDist):
    
    maskKeys = {'parallel'}
    
    @property
    def parallel(self):
        'Determines whether to operate in parallel' 

        return PARALLEL and getattr(self, '_parallel', True)
    
    @property
    def pool(self):
        'Returns a configured multiprocessing Pool'

        if self.parallel:
            if not hasattr(self, '_pool'):
                self._pool = multiprocessing.Pool(self.nWorkers)
            return self._pool            
            
        else:
            raise Exception('Cannot start parallel pool; multiprocessing seems to be unavailable')
    
    @property
    def nWorkers(self):
        'Returns the configured number of parallel workers'

        return min(getattr(self, '_nWorkers', 100), self.cpuCount)
    
    @property
    def cpuCount(self):
        'Returns the multiprocessing CPU count'

        if self.parallel:
            return multiprocessing.cpu_count()
        else:
            return 1
    
    @property
    def addFields(self):
        'Returns additional fields for the subProblem systemConfigs'

        fields = super(BaseMPDist, self).addFields
        
        remCap = self.cpuCount / self.nWorkers
        if (self.nWorkers < self.cpuCount) and remCap > 1:
            
            fields.update({'parallel': True, 'nWorkers': remCap})
            
        return fields
    
    def __mul__(self, rhs):
        '''
        Carries out the multiplication of the composite system
        by the right-hand-side vector(s).
        
        Args:
            rhs (array-like or list thereof): Source vectors
        
        Returns:
            u (iterator over np.ndarrays): Wavefields
        '''
        
        if isinstance(rhs, list):
            getRHS = lambda i: rhs[i]
        else:
            getRHS = lambda i: rhs
        
        if self.parallel:
            plist = []
            for i, sub in enumerate(self.subProblems):
                
                p = self.pool.apply_async(sub, (getRHS(i),))
                plist.append(p)
            
            u = (self.scaleTerm*p.get(PARTASK_TIMEOUT) for p in plist)
            
        else:
            u = (self.scaleTerm*(sub*getRHS(i)) for i, sub in enumerate(self.subProblems))
        
        return u


class BaseIPYDist(BaseDist):
    
    initMap = {
    #   Argument        Required    Rename as ...   Store as type
        'profile':      (False,     '_profile',     str),
    }
    
    maskKeys = {'profile'}
    
    @property
    def profile(self):
        'Returns the IPython parallel profile'

        return getattr(self, '_profile', 'default')
    
    @property
    def pClient(self):
        'Returns the IPython parallel client'

        if not hasattr(self, '_pClient'):
            from ipyparallel import Client
            self._pClient = Client(self.profile)
        return self._pClient

    @property
    def dView(self):
        'Returns a direct (multiplexing) view on the IPython parallel client'

        if not hasattr(self, '_dView'):
            self._dView = self.pClient[:]
        return self._dView
    
    @property
    def lView(self):
        'Returns a load-balanced view on the IPython parallel client'

        if not hasattr(self, '_lView'):
            self._lView = self.pClient.load_balanced_view()
        return self._lView
    
    @property
    def nWorkers(self):
        'Returns the configured number of parallel workers'

        return len(self.pClient.ids)


class MultiFreq(BaseMPDist):
    '''
    Wrapper to carry out forward-modelling using the stored
    discretization over a series of frequencies.
    '''
    
    initMap = {
    #   Argument        Required    Rename as ...   Store as type
        'freqs':        (True,      None,           list),
    }
    
    maskKeys = {'freqs'}
    
    @property
    def spUpdates(self):
        'Updates for frequency subProblems'

        vals = []
        for freq in self.freqs:
            spUpdate = {'freq': freq}
            spUpdate.update(self.addFields)
            vals.append(spUpdate)
        return vals
    

class SerialMultiFreq(MultiFreq):
    '''
    Wrapper to carry out forward-modelling using the stored
    discretization over a series of frequencies. Enforces
    serial execution.
    '''
    
    @property
    def parallel(self):
        'Determines whether to operate in parallel' 

        return False
    
    @property
    def addFields(self):
        'Returns additional fields for the subProblem systemConfigs'

        return {}
