import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { LogOut, User as UserIcon, PlusCircle } from 'lucide-react'
import { API_BASE_URL } from '../lib/api'

export default function Dashboard() {
  const { user, signOut, getAccessToken } = useAuth()
  const [profile, setProfile] = useState<any>(null)
  const [sessions, setSessions] = useState<any[]>([])
  
  useEffect(() => {
    async function fetchData() {
      const token = await getAccessToken()
      if (!token) return
      
      try {
        const [profileRes, sessionsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/profiles/me`, {
            headers: { Authorization: `Bearer ${token}` }
          }),
          fetch(`${API_BASE_URL}/api/v1/interviews/`, {
            headers: { Authorization: `Bearer ${token}` }
          })
        ])
        
        if (profileRes.ok) setProfile(await profileRes.json())
        if (sessionsRes.ok) setSessions(await sessionsRes.json())
      } catch (err) {
        console.error("Failed to fetch dashboard data", err)
      }
    }
    
    fetchData()
  }, [])

  return (
    <div>
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <span className="text-xl font-bold text-blue-600">AI Interviewer</span>
            </div>
            <div className="flex items-center space-x-4">
              <Link to="/profile" className="text-gray-600 hover:text-gray-900 flex items-center space-x-1">
                <UserIcon size={18} />
                <span>Profile</span>
              </Link>
              <button 
                onClick={signOut}
                className="text-gray-600 hover:text-gray-900 flex items-center space-x-1"
              >
                <LogOut size={18} />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-10 px-4 sm:px-6 lg:px-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
            <p className="mt-1 text-gray-500">
              Welcome back, {profile?.full_name || user?.email}
            </p>
          </div>
          <Link 
            to="/interviews/new"
            className="flex items-center space-x-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium shadow-sm transition"
          >
            <PlusCircle size={20} />
            <span>Start New Interview</span>
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="col-span-1 bg-white p-6 rounded-xl shadow-sm border border-gray-100">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Your Profile</h2>
            {!profile ? (
              <div className="text-center py-6">
                <p className="text-sm text-gray-500 mb-4">You haven't set up your profile yet.</p>
                <Link to="/profile" className="text-blue-600 text-sm font-medium hover:underline">Complete Profile &rarr;</Link>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-500 text-sm">Level</span>
                  <span className="font-medium text-gray-900 capitalize">{profile.confirmed_level || 'Not set'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500 text-sm">Experience</span>
                  <span className="font-medium text-gray-900">{profile.years_of_experience || 0} years</span>
                </div>
              </div>
            )}
          </div>

          <div className="col-span-2 bg-white p-6 rounded-xl shadow-sm border border-gray-100">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Sessions</h2>
            {sessions.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-lg">
                <p className="text-gray-500">No interview sessions found.</p>
                <Link to="/interviews/new" className="text-blue-600 font-medium hover:underline mt-2 inline-block">Start one now</Link>
              </div>
            ) : (
              <div className="divide-y divide-gray-100">
                {sessions.map(session => (
                  <div key={session.id} className="py-4 flex justify-between items-center">
                    <div>
                      <p className="font-medium text-gray-900">{session.role} <span className="text-xs ml-2 px-2 py-1 bg-gray-100 rounded-full capitalize">{session.level}</span></p>
                      <p className="text-sm text-gray-500 mt-1">{new Date(session.created_at).toLocaleDateString()}</p>
                    </div>
                    <Link to={`/interviews/${session.id}`} className="text-blue-600 text-sm font-medium hover:underline">
                      View details
                    </Link>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
