import { createBrowserRouter } from 'react-router-dom'

import { Shell } from '@/app/Shell'
import { Activity } from '@/screens/Activity'
import { Ask } from '@/screens/Ask'
import { Onboarding } from '@/screens/Onboarding'
import { Radar } from '@/screens/Radar'
import { Today } from '@/screens/Today'
import { WhatIf } from '@/screens/WhatIf'

export const router = createBrowserRouter([
  { path: '/', element: <Onboarding /> },
  {
    element: <Shell />,
    children: [
      { path: 'today', element: <Today /> },
      { path: 'activity', element: <Activity /> },
      { path: 'whatif', element: <WhatIf /> },
      { path: 'ask', element: <Ask /> },
      { path: 'radar', element: <Radar /> },
    ],
  },
])
