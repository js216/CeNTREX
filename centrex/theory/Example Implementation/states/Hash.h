#ifndef HASH_H
#define HASH_H

#include "BasisState.h"

// hash function
struct BasisState_hash {
   std::size_t operator()(const BasisState& ket) const
   {
      std::size_t result = 0;
      for (auto elem : ket.data)
         result += std::hash<std::string>()(elem.first);
      return result;
   }
};

#endif
