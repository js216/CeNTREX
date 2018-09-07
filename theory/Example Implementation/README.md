# Example Implementation

A quantum state is naturally represented as a C++ object, presenting a unified
interface regardless of the underlying representation, i.e. the chosen basis or
the way that basis is implemented on the computer. Likewise, an operator is a
function that maps from quantum states to quantum states and C++ allows us to
express this relation directly in the code.

Nonetheless, it is useful to leave the chosen basis in plain view; for example,
when adding two quantum states, the programmer needs to know what basis the
result and the two operands will be. The idiomatic way to express that is to let
a quantum state be a template class, templated by the basis. For example, a
state object `obj`, represented in a basis `BasisState`, is declared as follows:

    State<BasisState> obj;

Regardless of the basis, several basic operations are defined for a  `State<>`
object. For example, given two such objects `obj1` and `obj2`, we can for a
symmetric superposition

    State<> sup = (obj1 + obj2) / sqrt(2);

I have overloaded the operators `==`, `!=`, `+=`, `-=`, `*=`, `/=`, `*`, `/`,
`+`, `-` with sensible meanings. As in the above example, dividing by a number
divides the amplitudes of all components of a quantum state by that number;
addition of two states is the superposition state; a product of two states is
their inner product, and so on. See `states/State.h` for the implementation.

Much like `State<>`, the `BasisState` is also a user-defined type representing a
basis state in a given basis. Only the equality and inner product operations are
defined for such a state; for instance, a superposition of two different basis
states would not be a basis state.

However, the implementation (as given in `states/BasisState.h`) does not define
the basis. To this end, the expected use of the `BasisState` class is as a base
class. For example, in `bases/DecoupledBasis.h`, I define the type
`DecoupledBasis`, derived from `BasisState`, with a constructor that takes all
the quantum numbers, and puts them in the `data` data member:

    DecoupledBasis(double J, double mJ, double I1, double m1, double I2, double m2);
