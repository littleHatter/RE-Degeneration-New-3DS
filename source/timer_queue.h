#pragma once
#include <cstdint>
#include <vector>
#include <algorithm>

// Single-threaded guest timers. Deadlines use the same monotonic clock as TimerGetMs.
class TimerQueue {
public:
 struct Event { uint64_t id,due; uint32_t callback,user; };
 bool Add(uint64_t now,uint32_t delay,uint32_t callback,uint32_t user) {
  if(!callback||events.size()>=256)return false;
  events.push_back({++serial,now+delay,callback,user});return true;
 }
 uint64_t Generation() const {return serial;}
 bool TakeDue(uint64_t now,uint64_t generation,Event& out) {
  auto best=events.end();
  for(auto it=events.begin();it!=events.end();++it)
   if(it->due<=now&&it->id<=generation&&(best==events.end()||it->due<best->due||(it->due==best->due&&it->id<best->id)))best=it;
  if(best==events.end())return false;
  out=*best;events.erase(best);return true;
 }
private:
 std::vector<Event> events;uint64_t serial=0;
};
